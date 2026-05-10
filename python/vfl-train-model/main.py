import pandas as pd
import numpy as np
import sys
import os
import json
import torch
import torch.nn as nn
import torch.optim as optim
from google.protobuf.struct_pb2 import Struct
from dynamos.ms_init import NewConfiguration
from dynamos.signal_flow import signal_continuation, signal_wait
from dynamos.logger import InitLogger
import rabbitMQ_pb2 as rabbitTypes

from google.protobuf.empty_pb2 import Empty
import microserviceCommunication_pb2 as msCommTypes
import threading
from opentelemetry.context.context import Context

np.set_printoptions(threshold=sys.maxsize)

# --- DYNAMOS Interface code At the TOP ---------------------------
if os.getenv('ENV') == 'PROD':
    import config_prod as config
else:
    import config_local as config

logger = InitLogger()
# tracer = InitTracer(config.service_name, config.tracing_host)

# Events to start the shutdown of this Microservice, can be used to call 'signal_shutdown'
stop_event = threading.Event()
stop_microservice_condition = threading.Condition()

# Events to make sure all services have started before starting to process a message
# Might be overkill, but good practice
wait_for_setup_event = threading.Event()
wait_for_setup_condition = threading.Condition()

ms_config = None
vfl_server = None

# --- END DYNAMOS Interface code At the TOP ----------------------

# ---- LOCAL TEST SETUP OPTIONAL!

# Go into local test code with flag '-t'
# parser = argparse.ArgumentParser()
# parser.add_argument("-t", "--test", action='store_true')
# args = parser.parse_args()
# test = args.test

#region Helpers

def load_data(file_path) -> pd.DataFrame:
    DATA_STEWARD_NAME = os.getenv("DATA_STEWARD_NAME").lower()

    file_name = f"{file_path}/outcomeData.csv"

    if DATA_STEWARD_NAME == "":
        logger.error("DATA_STEWARD_NAME not set.")
        file_name = f"{file_path}Data.csv"

    try:
        data = pd.read_csv(file_name, delimiter=',')
        logger.debug("after read csv")
    except FileNotFoundError:
        logger.error(f"CSV file for table {file_name} not found.")
        return None

    return data

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

def extract_data(request: rabbitTypes.Request, property_name: str):
    try:
        return request.data[property_name]
    except Exception as e:
        logger.error(f"Problem occured while extracting [{property_name}]: {e}")
        return None

def extract_number_from_data(request: rabbitTypes.Request, property_name: str):
    prop = extract_data(request, property_name)
    return prop.number_value if (prop != None) else None 

def extract_array_from_data(request: rabbitTypes.Request, property_name: str):
    prop = extract_data(request, property_name)
    
    if (prop != None):
        prop_str = prop.string_value
        return deserialise_array(prop_str)
    else:
        return None

#endregion

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

    def sample_data(self, sample_batch_size):
        try:
            data_sample = self.data.sample(int(sample_batch_size))
            self.set_labels(data_sample["Survived"])

            data = Struct()
            data.update({"sample_batch_indexes": serialise_array(np.array(data_sample.index))})

            return data
        except Exception as e:
            logger.info(f"Error occurred while sampling data: {e}")

    def set_labels(self, data):
        self.labels = torch.tensor(data.values).float().unsqueeze(1)

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

    def aggregate_fit(self, results):
        global server_configuration

        try:
            embedding_results = [
                torch.from_numpy(embedding.copy())
                for embedding in results
            ]
        except Exception as e:
            logger.info(f"Converting the results to torch failed: {e}")

        try:
            embeddings_aggregated = torch.cat(embedding_results, dim=1)
            self.embeddings = embeddings_aggregated.detach().requires_grad_()
        except Exception as e:
            logger.info(f"Running gradient descent failed: {e}")

        self._calculate_loss()

        try:
            gradients = self.embeddings.grad.split([4, 4, 4], dim=1)
            np_gradients = [serialise_array(grad.numpy()) for grad in gradients]
        except Exception as e:
            logger.info(f"Converting the gradients failed: {e}")

        data = Struct()
        data.update({"gradients": np_gradients}) 

        return data
    
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

#region Request handlers

def handle_vflAggregateRequest(msComm):
    global ms_config
    global vfl_server

    request = rabbitTypes.Request()
    msComm.original_request.Unpack(request)

    try:
        data = request.data["embeddings"]
        logger.debug(f"Received data: {data}")
        # logger.debug(f"Embedding len: {len(data)}")
        clients_embeddings = [deserialise_array(
            embeddings.string_value
            ) for embeddings in data.list_value.values]
        
    except Exception as e:
        logger.error(f"Errored when deserialising client data: {e}")

    data = vfl_server.aggregate_fit(clients_embeddings)

    ms_config.next_client.ms_comm.send_data(msComm, data, {})

def handle_vflShutdownRequest(msComm):
    global ms_config

    logger.info("Received vflShutdownRequest, shutting down service.")
    ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})
    signal_continuation(stop_event, stop_microservice_condition)

def handle_vflPingRequest(msComm):
    logger.info("Received a vflPingRequest.")
    ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})

def handle_vflSampleBatchRequest(msComm, request):
    global ms_config
    global vfl_server
    try:
        sample_batch_size = extract_number_from_data(request, "sample_batch_size")

        data = vfl_server.sample_data(sample_batch_size)

        ms_config.next_client.ms_comm.send_data(msComm, data, {})
    except Exception as e:
        logger.info(f"Error occurred while handling vflSampleBatchRequest: {e}")

def handle_vflLocalUpdateRequest(msComm, request):
    global ms_config
    global vfl_server

    accuracies = []
    communication_frequency = int(extract_number_from_data(request, "communication_frequency"))
    cycle = -1

    try:
        for cycle in range(communication_frequency):
            accuracy = vfl_server.local_update()
            accuracies.append(accuracy)
    except Exception as e:
        logger.info(f"Error occurred in cycle [{cycle}]: {e}")

    data = Struct()
    data.update({"accuracies": accuracies})

    ms_config.next_client.ms_comm.send_data(msComm, data, {})

#endregion

# ---  DYNAMOS Interface code At the Bottom --------

def request_handler(msComm: msCommTypes.MicroserviceCommunication,
                    ctx: Context = None):
    global ms_config

    logger.info(f"Received original request type: {msComm.request_type}")

    # Ensure all connections have finished setting up before processing data
    signal_wait(wait_for_setup_event, wait_for_setup_condition)

    try:
        request = rabbitTypes.Request()
        msComm.original_request.Unpack(request)
    except Exception as e:
        logger.error(f"Unexpected original request received: {e}")
        ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})
        return Empty()

    DATA_STEWARD_NAME = os.getenv("DATA_STEWARD_NAME").lower()

    if DATA_STEWARD_NAME != "server":
        if request.type == "vflShutdownRequest":
            handle_vflShutdownRequest(msComm)
        else:
            logger.info(f"Received request: {request.type}. This is the client (not server), relaying request.")
            ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})

    else:
        if request.type == "vflAggregateRequest":
            handle_vflAggregateRequest(msComm)

        elif request.type == "vflPingRequest":
            handle_vflPingRequest(msComm)

        elif request.type == "vflShutdownRequest":
            handle_vflShutdownRequest(msComm)
        
        elif request.type == "vflSampleBatchRequest":
            handle_vflSampleBatchRequest(msComm, request)

        elif request.type == "vflLocalUpdateRequest":
            handle_vflLocalUpdateRequest(msComm, request)

        return Empty()


def main():
    global config
    global ms_config
    global vfl_server

    data = load_data(config.dataset_filepath)
    vfl_server = VFLServer(data)

    ms_config = NewConfiguration(
        config.service_name, config.grpc_addr, request_handler)

    # Signal the message handler that all connections have been created
    signal_continuation(wait_for_setup_event, wait_for_setup_condition)

    # Wait for the end of processing to shutdown this Microservice
    try:
        signal_wait(stop_event, stop_microservice_condition)

    except KeyboardInterrupt:
        logger.debug("KeyboardInterrupt received, stopping server...")
        signal_continuation(stop_event, stop_microservice_condition)

    ms_config.stop(2)
    logger.debug(f"Exiting {config.service_name}")
    sys.exit(0)

# ---  END DYNAMOS Interface code At the Bottom -----------------


if __name__ == "__main__":
    main()
