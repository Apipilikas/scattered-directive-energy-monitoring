import pandas as pd
import numpy as np
import sys
import os
import io
import json
import torch
import torch.nn as nn
from collections import OrderedDict
from sklearn.preprocessing import StandardScaler
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

# --- END DYNAMOS Interface code At the TOP ----------------------

# ---- LOCAL TEST SETUP OPTIONAL!

# Go into local test code with flag '-t'
# parser = argparse.ArgumentParser()
# parser.add_argument("-t", "--test", action='store_true')
# args = parser.parse_args()
# test = args.test

# --------------------------------


#region Helpers

def load_data(file_path):
    DATA_STEWARD_NAME = os.getenv("DATA_STEWARD_NAME").lower()

    file_name = f"{file_path}/{DATA_STEWARD_NAME}Data.csv"

    if DATA_STEWARD_NAME == "":
        logger.error("DATA_STEWARD_NAME not set.")
        file_name = f"{file_path}Data.csv"

    try:
        data = pd.read_csv(file_name, delimiter=',')
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
    logger.info(string, encoded_data)
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


class ClientModel(nn.Module):
    def __init__(self, input_size):
        super().__init__()
        self.fc = nn.Linear(input_size, 4)

    def forward(self, x):
        return self.fc(x)


class VFLClient():
    def __init__(self, data, learning_rate=0.01, model_state=None, optimiser_state=None):
        self.data = data
        self.model = ClientModel(data.shape[1])
        if model_state is not None:
            self.model.load_state_dict(model_state)

        self.optimiser = None

    def set_labels_from_sample(self, sample_indexes):
        sample_data = self.data[self.data.index.isin(sample_indexes)]
        self.set_labels(sample_data)

    def set_labels(self, data):
        try:
            self.labels = torch.tensor(StandardScaler().fit_transform(data)).float()
        except Exception as e:
            logger.error(f"Error occurred while setting labels: {e}")

    def create_optimiser(self, learning_rate):
        if self.optimiser is None:
            self.optimiser = torch.optim.SGD(
                self.model.parameters(), lr=learning_rate)

    def train_model(self):
        self.embedding = self.model(self.labels)
        return serialise_array(self.embedding.detach().numpy())

    def gradient_descent(self, gradients):
        if self.optimiser is None:
            logger.error("Optimiser is not defined.")

        try:
            self.model.zero_grad()
            current_embedding = self.model(self.labels)
            current_embedding.backward(torch.from_numpy(gradients))
            self.optimiser.step()
        except Exception as e:
            logger.error(f"Error occurred: {e}")


#region Request handlers

def handle_vflShutdownRequest(msComm: msCommTypes.MicroserviceCommunication):
    global ms_config

    ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})
    signal_continuation(stop_event, stop_microservice_condition)

def handle_vflTrainRequest(msComm: msCommTypes.MicroserviceCommunication, 
                           request: rabbitTypes.Request):
    global ms_config
    global vfl_client
    
    try:
        # sample_indexes = request.data["sample_batch_indexes"].string_value
        sample_indexes = extract_array_from_data(request, "sample_batch_indexes")
        vfl_client.set_labels_from_sample(sample_indexes)
    except Exception as e:
        logger.error(f"Error occurred while getting sample indexes: {e}")

    try:
        embeddings = vfl_client.train_model()
        data = Struct()
        data.update({"embeddings":  embeddings})
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        data = Struct()

    ms_config.next_client.ms_comm.send_data(msComm, data, {})

def handle_vflGradientDescentRequest(msComm: msCommTypes.MicroserviceCommunication, 
                                     request: rabbitTypes.Request):
    global ms_config
    global vfl_client

    # Extract learning rate
    try:
        learning_rate = request.data["learning_rate"].number_value
        vfl_client.create_optimiser(learning_rate)
    except Exception:
        vfl_client.create_optimiser(0.05)

    # Extract gradients
    try:
        gradients = request.data["gradients"].string_value
        gradients = deserialise_array(gradients)
    except Exception as e:
        logger.error(f"Gradients did not get parsed properly: {e}")
        logger.info(msComm.data)
        gradients = None

    communication_frequency = int(extract_number_from_data(request, "communication_frequency"))
    cycle = -1

    try:
        for cycle in range(communication_frequency):
            vfl_client.gradient_descent(gradients)
    except Exception as e:
        logger.error(f"Unexpected error in cycle [{cycle}]: {e}")

    try:
        data = Struct()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")

    ms_config.next_client.ms_comm.send_data(msComm, data, {})

def handle_vflPingRequest(msComm: msCommTypes.MicroserviceCommunication):
    global ms_config
    
    ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})

#endregion

#region DYNAMOS interface

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

    if DATA_STEWARD_NAME == "server":
        if request.type == "vflShutdownRequest":
            handle_vflShutdownRequest(msComm)
        else:
            logger.info("This is the server (not client), relaying request.")
            ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})
    else:
        if request is not None:
            logger.info(f"Received request: {request.type}. This is the client.")
            if request.type == "vflTrainRequest":
                handle_vflTrainRequest(msComm, request)
                
            elif request.type == "vflGradientDescentRequest":
                handle_vflGradientDescentRequest(msComm, request)

            elif request.type == "vflShutdownRequest":
                handle_vflShutdownRequest(msComm)

            elif request.type == "vflPingRequest":
                handle_vflPingRequest(msComm)

            else:
                logger.error(f"An unknown request_type: {msComm.data.type}")

            return Empty()

#endregion

def main():
    global config
    global ms_config
    global vfl_client

    try:
        data = load_data(config.dataset_filepath)
        vfl_client = VFLClient(data)
    except Exception as e:
        logger.error(f"Error occurred: {e}")

    ms_config = NewConfiguration(
        config.service_name, config.grpc_addr, request_handler)

    signal_continuation(wait_for_setup_event, wait_for_setup_condition)

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
