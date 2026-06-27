import pandas as pd
import numpy as np
import sys
import os
import io
import json
import torch
import torch.nn as nn
import torch.optim as optim
from collections import OrderedDict
from sklearn.preprocessing import StandardScaler


# ---------------------- SET SEED FOR REPRODUCIBILITY ----------------------
SEED = 0
np.random.seed(SEED)
torch.manual_seed(SEED)
# --------------------------------------------------------------------------


# 1. LOAD DATASETS
server_data = pd.read_csv("data/train/outcomeData.csv", delimiter=',', index_col=0)

client1_data = pd.read_csv("data/train/clientoneData.csv", delimiter=',', index_col=0)
client1_data_test = pd.read_csv("data/test/clientoneData.csv", delimiter=',', index_col=0)

client2_data = pd.read_csv("data/train/clienttwoData.csv", delimiter=',', index_col=0)
client2_data_test = pd.read_csv("data/test/clienttwoData.csv", delimiter=',', index_col=0)

client3_data = pd.read_csv("data/train/clientthreeData.csv", delimiter=',', index_col=0)
client3_data_test = pd.read_csv("data/test/clientthreeData.csv", delimiter=',', index_col=0)

# Attempt to load test outcome data for PassengerId mapping during evaluation
try:
    server_data_test = pd.read_csv("data/test/outcomeData.csv", delimiter=',', index_col=0)
except Exception:
    server_data_test = client1_data_test  # Safe fallback if file doesn't exist

# Maintain distinct datasets (Do NOT overwrite with a merged DataFrame)
client_datasets = [client1_data, client2_data, client3_data]
test_datasets = [client1_data_test, client2_data_test, client3_data_test]

# Sanity check that training indices match the server
for i, c_df in enumerate(client_datasets):
    assert c_df.index.equals(server_data.index), f"Client {i+1} index does not match server!"


# ---------------------- SIMULATION CONFIGURATION ----------------------
NOF_CLIENTS = 3          # Set to 3 to train all available clients
REMOVE_CLIENT_ROUND = -1 # Round to drop a client (-1 to disable)
SHRINK_SERVER = True     # Truncate weights vs reinstantiating

ADD_CLIENT_ROUND = -1    # Round to add a client (-1 to disable)
ADD_CLIENT_CLEAN = False 

TOTAL_ROUNDS = 180
SERVER_CHECKPOINT_PATH = "server_state.pth"
# ----------------------------------------------------------------------

np.set_printoptions(threshold=sys.maxsize)


class ClientModel(nn.Module):
    def __init__(self, input_size):
        super().__init__()
        self.fc = nn.Linear(input_size, 4)

    def forward(self, x):
        return self.fc(x)


def serialise_array(array):
    return json.dumps([
        str(array.dtype),
        array.tobytes().decode("latin1"),
        array.shape
    ])


def deserialise_array(string, hook=None):
    encoded_data = json.loads(string, object_pairs_hook=hook)
    dataType = np.dtype(encoded_data[0])
    dataArray = np.frombuffer(encoded_data[1].encode("latin1"), dataType)

    if len(encoded_data) > 2:
        return dataArray.reshape(encoded_data[2])

    return dataArray


class VFLClient():
    def __init__(self, data, learning_rate=0.01, model_state=None):
        # Lock training feature names to survive test-set column discrepancies
        self.feature_columns = data.columns
        
        # Persistent Scaler fit strictly on training data
        self.scaler = StandardScaler()
        scaled_data = self.scaler.fit_transform(data)
        
        self.data = torch.tensor(scaled_data).float()
        self.model = ClientModel(self.data.shape[1])
        
        if model_state is not None:
            self.model.load_state_dict(model_state)

        self.optimiser = None
        self.embedding = None

    def create_optimiser(self, learning_rate):
        if self.optimiser is None:
            self.optimiser = torch.optim.SGD(self.model.parameters(), lr=learning_rate)

    def train_model(self):
        self.embedding = self.model(self.data)
        return serialise_array(self.embedding.detach().numpy())

    def gradient_descent(self, gradients):
        if self.optimiser is None:
            print("Optimiser is not defined.")
            return

        try:
            self.model.zero_grad()
            self.embedding.backward(torch.from_numpy(gradients))
            self.optimiser.step()
        except Exception as e:
            print(f"Error occurred during client backprop: {e}")

    def evaluate_model(self, test_data):
        # Force exact feature alignment (drops unexpected test index columns)
        aligned_test = test_data[self.feature_columns]
        scaled_test = self.scaler.transform(aligned_test)
        
        data = torch.tensor(scaled_test).float()
        self.model.eval()

        with torch.no_grad():
            embedding = self.model(data)
        self.model.train()

        return serialise_array(embedding.numpy())


def shrink_server_model(old_model, new_input_size):
    new_model = ServerModel(new_input_size)
    with torch.no_grad():
        new_model.fc.weight[:, :] = old_model.fc.weight[:, :new_input_size]
        new_model.fc.bias[:] = old_model.fc.bias[:]
    return new_model


class ServerModel(nn.Module):
    def __init__(self, input_size):
        super(ServerModel, self).__init__()
        self.fc = nn.Linear(input_size, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        x = self.fc(x)
        return self.sigmoid(x)


class VFLServer():
    def __init__(self, data, active_client_count):
        self.active_clients = active_client_count
        self.model = ServerModel(4 * self.active_clients) 
        self.optimizer = optim.SGD(self.model.parameters(), lr=0.01)
        self.criterion = nn.BCELoss()
        self.labels = torch.tensor(data["Survived"].values).float().unsqueeze(1)

    def aggregate_fit(self, results):
        try:
            embedding_results = [torch.from_numpy(emb.copy()) for emb in results]
            embeddings_aggregated = torch.cat(embedding_results, dim=1)
            embedding_server = embeddings_aggregated.detach().requires_grad_()
            
            output = self.model(embedding_server)
            loss = self.criterion(output, self.labels)
            
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()
        except Exception as e:
            print(f"Server forward/backward pass failed: {e}")

        try:
            grads = embedding_server.grad.split([4] * self.active_clients, dim=1)
            np_gradients = [serialise_array(grad.numpy()) for grad in grads]
        except Exception as e:
            print(f"Gradient splitting failed: {e}")

        with torch.no_grad():
            output = self.model(embedding_server)
            predicted = (output > 0.5).float()
            correct = (predicted == self.labels).sum().item()
            accuracy = correct / len(self.labels) * 100

        print(f"Accuracy achieved: {accuracy:.2f}%")
        return [{"accuracy": accuracy, "gradients": np_gradients}]
    
    def save_state(self, filepath):
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict()
        }, filepath)

    def load_state(self, filepath):
        state = torch.load(filepath)
        self.model.load_state_dict(state['model_state_dict'])
        self.optimizer.load_state_dict(state['optimizer_state_dict'])

    def evaluate_model(self, embeddings, test_data):
        self.model.eval()
        try:
            embedding_results = [torch.from_numpy(deserialise_array(emb)) for emb in embeddings]
            embeddings_aggregated = torch.cat(embedding_results, dim=1)
            
            with torch.no_grad():
                output = self.model(embeddings_aggregated)
                predicted = (output > 0.5).float()
                survived_predictions = predicted.cpu().numpy().astype(int).flatten()

            # Safely grab PassengerId whether it acts as a column or the index
            if "PassengerId" in test_data.columns:
                p_ids = test_data["PassengerId"].values
            else:
                p_ids = test_data.index.values
            
            os.makedirs("data", exist_ok=True)
            pd.DataFrame({
                "PassengerId": p_ids,
                "Survived": survived_predictions
            }).to_csv("data/testData.csv", index=False)
            print("Evaluation complete. Saved export to: data/testData.csv")
            
        except Exception as e:
            print(f"Evaluation failed: {e}")
            
        self.model.train()


# ---------------------- INITIALIZE SIMULATION ----------------------
all_clients = [VFLClient(df) for df in client_datasets]
clients = all_clients[:NOF_CLIENTS] 

vfl_server = VFLServer(server_data, active_client_count=NOF_CLIENTS)
train_results = []


# ---------------------- TRAINING LOOP ----------------------
for round_num in range(TOTAL_ROUNDS):
    print("--------------------------------------------------")
    print(f"Round {round_num + 1}")
    
    # Trigger Client Removal
    if round_num == REMOVE_CLIENT_ROUND:
        if NOF_CLIENTS > 1:
            NOF_CLIENTS -= 1
            clients.pop() 
            print(f"Client removed. Active clients: {NOF_CLIENTS}")
            vfl_server.save_state(SERVER_CHECKPOINT_PATH)

            if SHRINK_SERVER:
                old_model = vfl_server.model
                vfl_server.active_clients = NOF_CLIENTS
                vfl_server.model = shrink_server_model(old_model, 4 * NOF_CLIENTS)
            else:
                vfl_server = VFLServer(server_data, NOF_CLIENTS)

    # Trigger Client Addition
    if round_num == ADD_CLIENT_ROUND:
        if NOF_CLIENTS < len(all_clients):
            NOF_CLIENTS += 1
            if ADD_CLIENT_CLEAN:
                all_clients[NOF_CLIENTS - 1] = VFLClient(client_datasets[NOF_CLIENTS - 1])
            
            clients.append(all_clients[NOF_CLIENTS - 1])
            print(f"Client added. Active clients: {NOF_CLIENTS}")

            if os.path.isfile(SERVER_CHECKPOINT_PATH):
                vfl_server = VFLServer(server_data, NOF_CLIENTS)
                vfl_server.load_state(SERVER_CHECKPOINT_PATH)
            else:
                vfl_server = VFLServer(server_data, NOF_CLIENTS)

    # 1. Forward Pass (Clients -> Embeddings)
    raw_results = [c.train_model() for c in clients]
    deserialized_results = [deserialise_array(emb) for emb in raw_results]

    # 2. Server Aggregation & Loss
    data = vfl_server.aggregate_fit(deserialized_results)
    gradients = data[-1]['gradients']

    # 3. Backpropagate (Server -> Clients)
    for i, client_obj in enumerate(clients):
        client_obj.create_optimiser(0.05)
        client_obj.gradient_descent(deserialise_array(gradients[i]))

    train_results.append({
        "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "train_round": round_num + 1,
        "accuracy": data[-1]['accuracy'],
        "clients": NOF_CLIENTS
    })


# ---------------------- TESTING & EXPORT ----------------------
print("--------------------------------------------------")
print("Running Final Test Evaluation...")

# Dynamically slice test sets to match surviving active clients
active_test_sets = test_datasets[:len(clients)]

test_embeddings = [
    client.evaluate_model(active_test_sets[i])
    for i, client in enumerate(clients)
]

vfl_server.evaluate_model(test_embeddings, server_data_test)

os.makedirs("./run_dumps", exist_ok=True)
dump_filename = f"./run_dumps/vfl_test_results_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.json"

with open(dump_filename, "w") as f:
    json.dump({
        "metadata": {
            "total_rounds": TOTAL_ROUNDS,
            "REMOVE_CLIENT_ROUND": REMOVE_CLIENT_ROUND,
            "SHRINK_SERVER": SHRINK_SERVER,
            "ADD_CLIENT_ROUND": ADD_CLIENT_ROUND,
            "ADD_CLIENT_CLEAN": ADD_CLIENT_CLEAN,
        },
        "results": train_results
    }, f, indent=2)

print(f"Run dump successfully exported to {dump_filename}")