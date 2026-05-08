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
from google.protobuf.struct_pb2 import Struct, ListValue, Value


class ClientModel(nn.Module):
    def __init__(self, input_size):
        super().__init__()
        self.fc = nn.Linear(input_size, 4)

    def forward(self, x):
        return self.fc(x)


def serialise_dictionary(dictionary):
    buffer = io.BytesIO()
    torch.save(dictionary, buffer)

    return buffer.getvalue().decode("latin1")


def deserialise_dictionary(dictionary):
    data = json.loads(dictionary, object_pairs_hook=OrderedDict)

    return torch.load(io.BytesIO(data.encode("latin1")))


def serialise_array(array):
    return json.dumps([
        str(array.dtype),
        array.tobytes().decode("latin1"),
        array.shape])


def deserialise_array(string, hook=None):
    encoded_data = json.loads(string, object_pairs_hook=hook)
    dataType = np.dtype(encoded_data[0])
    dataArray = np.frombuffer(encoded_data[1].encode("latin1"), dataType)

    if len(encoded_data) > 2:
        return dataArray.reshape(encoded_data[2])

    return dataArray


class VFLClient():
    def __init__(self, data, learning_rate=0.01, model_state=None, optimiser_state=None):
        self.data = data
        self.model = ClientModel(self.data.shape[1])
        if model_state is not None:
            self.model.load_state_dict(model_state)

        self.optimiser = None
        self.create_optimiser(learning_rate)

    def create_optimiser(self, learning_rate):
        if self.optimiser is None:
            self.optimiser = torch.optim.SGD(
                self.model.parameters(), lr=learning_rate)

    def train_model(self):
        self.embedding = self.model(self.labels)
        return serialise_array(self.embedding.detach().numpy())

    def set_labels_from_sample(self, sample_indexes):
        sample_data = self.data[self.data.index.isin(sample_indexes)]
        self.set_labels(sample_data)

    def set_labels(self, data):
        self.labels = torch.tensor(StandardScaler().fit_transform(data)).float()

    def gradient_descent(self, gradients):
        print("Start vfl_evaluate")

        if self.optimiser is None:
            print("Optimiser is not defined.")

        try:
            self.model.zero_grad()
            # Re-evaluates the forward pass using current weights.
            current_embedding = self.model(self.labels)
            # Backpropagation.
            current_embedding.backward(torch.from_numpy(gradients))
            self.optimiser.step()
        except Exception as e:
            print(f"Error occurred: {e}")

        return "100% accuracy, buddy!"
    
    def evaluate_model(self):
        self.set_labels(self.data)
        self.model.eval()

        with torch.no_grad():
            embedding = self.model(self.labels)
        self.model.train()

        return serialise_array(embedding.numpy())


np.set_printoptions(threshold=sys.maxsize)


class ServerModel(nn.Module):
    def __init__(self, input_size):
        super(ServerModel, self).__init__()
        self.fc = nn.Linear(input_size, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        x = self.fc(x)
        return self.sigmoid(x)


class VFLServer():
    def __init__(self, data):
        self.model = ServerModel(12)
        # self.initial_parameters = ndarrays_to_parameters(
        #     [val.cpu().numpy()
        #      for _, val in server_configuration.model.state_dict().items()]
        # )
        self.optimizer = optim.SGD(self.model.parameters(), lr=0.01)
        self.criterion = nn.BCELoss()
        self.data = data
        # self.labels = torch.tensor(
        #     data["Survived"].values).float().unsqueeze(1)

    def sample_data(self):
        data_sample = self.data.sample(64)
        self.set_labels(data_sample["Survived"].values)

        data = Struct()
        data.update({"sample_indexes": serialise_array(np.array(data_sample.index))})

        return data

    def set_labels(self, values):
        self.labels = torch.tensor(values).float().unsqueeze(1)


    def _calculate_loss(self):
        try:
            # Passes the tensor through the server model.
            output = self.model(self.embeddings)
            # Using BCE (Binary Cross Entropy), calculates the loss. Basically, compares its predictions against the true labels.
            loss = self.criterion(output, self.labels)
            # Calculates the gradient of the loss function with respect to the predicted probabilities, 
            # enabling weight updates in binary classification tasks.
            loss.backward()
        except Exception as e:
            print(f"Running gradient descent 2 failed: {e}")
            print(f"{output}, {self.labels}")

        try:
            # TOFIX
            # Uses optimizer to adjust weights. This way reduces the error.
            self.optimizer.step()
            # Clears the gradients to prepare for the next round.
            self.optimizer.zero_grad()
        except Exception as e:
            print(f"Running gradient descent 3 failed: {e}")
        
        return output

    def get_gradients(self, results):
        global server_configuration

        try:
            # Convert the embeddings to PyTorch tensors to build computational graphs.
            embedding_results = [
                torch.from_numpy(embedding.copy())
                for embedding in results
            ]
        except Exception as e:
            print(f"Converting the results to torch failed: {e}")

        try:
            # Takes the three individual client tensors (N x 4) and concatenates them into a larger tensor N x 12
            embeddings_aggregated = torch.cat(embedding_results, dim=1)
            # Detaches tensors from clients to calculate gradients without knowing their roots.
            self.embeddings = embeddings_aggregated.detach().requires_grad_()
        except Exception as e:
            print(f"Running gradient descent 1 failed: {e}")

        self._calculate_loss()

        # Chops gradients back to N x 4 chunks, one for each client.
        grads = self.embeddings.grad.split([4, 4, 4], dim=1)
        # Converts to numpy.
        np_gradients = [serialise_array(grad.numpy()) for grad in grads]

        return np_gradients

    def local_update(self):
        output = self._calculate_loss()

        # Calculates the accuracy.
        with torch.no_grad():
            correct = 0
            predicted = (output > 0.5).float()

            correct += (predicted == self.labels).sum().item()

            accuracy = correct / len(self.labels) * 100

        # data = Struct()
        # data.update({"accuracy": accuracy})

        return accuracy
    
    def evaluate_model(self, embeddings):
        self.model.eval()
        
        try:
            embedding_results = [torch.from_numpy(deserialise_array(emb)) for emb in embeddings]
            embeddings_aggregated = torch.cat(embedding_results, dim=1)
            labels_tensor = torch.tensor(self.data["Survived"].values).float().unsqueeze(1)
            
            with torch.no_grad():
                output = self.model(embeddings_aggregated)
                predicted = (output > 0.5).float()
                correct = (predicted == labels_tensor).sum().item()
                accuracy = (correct / len(labels_tensor)) * 100
                
        except Exception as e:
            print(f"Evaluation failed: {e}")
            return 0.0
            
        self.model.train()
        return accuracy

    
def main():
    datac1 = pd.read_csv('../python/vfl-train/datasets/clientoneData.csv')
    datac2 = pd.read_csv('../python/vfl-train/datasets/clienttwoData.csv')
    datac3 = pd.read_csv('../python/vfl-train/datasets/clientthreeData.csv')
    datas = pd.read_csv('../python/vfl-train-model/datasets/outcomeData.csv')

    client1 = VFLClient(datac1)
    client2 = VFLClient(datac2)
    client3 = VFLClient(datac3)
    server = VFLServer(datas)

    sample_indexes = deserialise_array(server.sample_data()["sample_indexes"])
    print(sample_indexes)
    
    accs = []
    q = 15

    # If is time for sychronization, then send vflSampleBatchRequest to server
	# Then send this to clients, perform a training. return intermediate embeddings to server.
	# Server perform aggregation and send gradients back to clients. 
    # Then clients perform for Q times gradient descent.
	# The clients perform a independent gradient discend. They repeatedly refine their local parameters using 
    # the exact mini batch dataset.
	# When it is finished, they perform the same cycle once again.
    gradients = []
    for i in range(180):
        if (i % q) == 0:
            # Sample a mini batch
            sample_indexes = deserialise_array(server.sample_data()["sample_indexes"])

            client1.set_labels_from_sample(sample_indexes)
            client2.set_labels_from_sample(sample_indexes)
            client3.set_labels_from_sample(sample_indexes)

            # Compute intermediate embeddings
            embeddings = [
            client1.train_model(),
            client2.train_model(),
            client3.train_model()
            ]

            embeddings = [deserialise_array(embedding) for embedding in embeddings]

            # Send them to the server. 
            gradients = server.get_gradients(embeddings)
            

        client1.gradient_descent(deserialise_array(gradients[0]))
        client2.gradient_descent(deserialise_array(gradients[1]))
        client3.gradient_descent(deserialise_array(gradients[2]))

        accuracy = server.local_update()
        accs.append(accuracy)

    test_embeddings = [
        client1.evaluate_model(),
        client2.evaluate_model(),
        client3.evaluate_model()
    ]

    final_accuracy = server.evaluate_model(test_embeddings)

    print(accs)
    print(final_accuracy)

if __name__ == "__main__":
    main()