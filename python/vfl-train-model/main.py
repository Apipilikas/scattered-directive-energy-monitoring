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
import queue

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

def serialise_dictionary(dictionary):
    return json.dumps(dictionary)

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
        self.accuracies = {}
        self.current_cycle = 0

        self.training_lock = threading.Lock()
        self.training_thread = None

        self.labels = {}
        self.embeddings = {}
        self.embeddings_queue = queue.Queue()
        self.gradients_queue = queue.Queue()

        threading.Thread(target=self._execute_training_process_async).start()

    def _execute_training_process_async(self):
        while True:
            try:
                cycle = self.embeddings_queue.get_nowait()
                gradients = self.aggregate_fit(cycle)
                self.gradients_queue.put((cycle, gradients))
                self.local_update(cycle, 15)
            except queue.Empty:
                pass
            
    def put_embeddings(self, cycle, embeddings):
        try:
            embedding_results = [
                torch.from_numpy(embedding.copy())
                for embedding in embeddings
            ]

        except Exception as e:
            logger.info(f"Converting the results to torch failed: {e}")

        try:
            embeddings_aggregated = torch.cat(embedding_results, dim=1)
            current_embeddings = embeddings_aggregated.detach().requires_grad_()
        except Exception as e:
            logger.info(f"Running gradient descent failed: {e}")

        self.embeddings[cycle] = current_embeddings
        self.embeddings_queue.put(cycle)

    def is_training_in_progress(self):
        return not self.training_thread is None and self.training_thread.is_alive()

    def wait_for_training_to_finish(self):
        if (self.is_training_in_progress()):
            self.training_thread.join()

    def sample_data(self, sample_batch_size):
        try:
            data_sample = self.data.sample(int(sample_batch_size))

            data = Struct()
            data.update({"sample_batch_indexes": serialise_array(np.array(data_sample.index))})

            return data
        except Exception as e:
            logger.info(f"Error occurred while sampling data: {e}")

    def set_labels_from_sample(self, cycle, sample_indexes):
        sample_data = self.data.loc[sample_indexes]
        return self.set_labels(cycle, sample_data["Survived"])

    def set_labels(self, cycle, data):
        logger.info(f"Labels set for cycle {cycle}.")

        calculated_labels = torch.tensor(data.values).float().unsqueeze(1)
        self.labels[cycle] = calculated_labels

        return calculated_labels

    def aggregate_fit(self, cycle):
        logger.info(f"Aggregate fit for cycle {self.current_cycle}.")
        global server_configuration

        labels = self.labels[cycle]
        embeddings = self.embeddings[cycle]
        
        with self.training_lock:
            output = self.model(embeddings)
            loss = self.criterion(output, labels)
            
            self.optimizer.zero_grad()
            loss.backward()

        try:
            gradients = embeddings.grad.split([4, 4, 4], dim=1)
            np_gradients = [serialise_array(grad.numpy()) for grad in gradients]
        except Exception as e:
            logger.info(f"Converting the gradients failed: {e}")

        # data = Struct()
        # data.update({"gradients": np_gradients})
        # data.update({"accuracies": serialise_dictionary(self.accuracies)})

        return np_gradients
    
    def _local_update(self, embeddings, labels):
        with self.training_lock:
            output = self.model(embeddings)
            loss = self.criterion(output, labels)

            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()

            # Calculates the accuracy.
            with torch.no_grad():
                correct = 0
                predicted = (output > 0.5).float()

                correct += (predicted == labels).sum().item()

                accuracy = correct / len(labels) * 100

        return accuracy
    
    def local_update(self, cycle, communication_frequency = 1):
        labels = self.labels[cycle]
        embeddings = self.embeddings[cycle]

        try:
            for _ in range(communication_frequency):
                accuracy = self._local_update(embeddings, labels)
            
            self.accuracies[cycle] = accuracy # Only the last accuracy
            logger.info(f"Finished local update for cycle {self.current_cycle}.")
        except Exception as e:
            logger.error(f"Error occurred in cycle [{cycle}]: {e}")

    def local_update_async(self, cycle, communication_frequency):
        if not self.is_training_in_progress():
            self.training_thread = threading.Thread(
                target=self.local_update,
                args=(cycle, communication_frequency,)
            )
            self.training_thread.start()

    def get_latest_gradients(self):
        data = Struct()

        try:
            cycle, gradients = self.gradients_queue.get_nowait()
            logger.debug("Latest gradients have been fetched.")
            data.update({"cycle": cycle})
            data.update({"gradients": gradients})
            data.update({"accuracies": serialise_dictionary(self.accuracies)})
        except queue.Empty:
            logger.debug("No gradients have been found!")

        return data
    
#region Request handlers

def handle_vflAggregateRequest(msComm, request):
    global ms_config
    global vfl_server

    try:
        data = request.data["embeddings"]

        clients_embeddings = [deserialise_array(
            embeddings.string_value
            ) for embeddings in data.list_value.values]
        
        sample_indexes = extract_array_from_data(request, "sample_batch_indexes")
        communication_frequency = int(extract_number_from_data(request, "communication_frequency"))
        cycle = int(extract_number_from_data(request, "cycle"))
    except Exception as e:
        logger.error(f"Errored when deserialising client data: {e}")

    # vfl_server.wait_for_training_to_finish()

    # vfl_server.current_cycle = cycle

    vfl_server.set_labels_from_sample(cycle, sample_indexes)
    vfl_server.put_embeddings(cycle, clients_embeddings)

    data = vfl_server.get_latest_gradients()

    ms_config.next_client.ms_comm.send_data(msComm, data, {})

    # vfl_server.local_update_async(communication_frequency)

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
        gradients_data = vfl_server.get_latest_gradients()

        data.MergeFrom(gradients_data)

        ms_config.next_client.ms_comm.send_data(msComm, data, {})
    except Exception as e:
        logger.info(f"Error occurred while handling vflSampleBatchRequest: {e}")

def handle_vflGetAccuraciesRequest(msComm):
    global ms_config
    global vfl_server

    try:
        data = Struct()
        data.update({"accuracies": serialise_dictionary(vfl_server.accuracies)})

        ms_config.next_client.ms_comm.send_data(msComm, data, {})
    except Exception as e:
        logger.error(f"Error occurred while handling vflGetAccuraciesRequest: {e}")

# def handle_vflLocalUpdateRequest(msComm, request):
#     global ms_config
#     global vfl_server

#     accuracies = []
#     communication_frequency = int(extract_number_from_data(request, "communication_frequency"))
#     cycle = -1

#     try:
#         for cycle in range(communication_frequency):
#             accuracy = vfl_server.local_update()
#             accuracies.append(accuracy)
#     except Exception as e:
#         logger.info(f"Error occurred in cycle [{cycle}]: {e}")

#     data = Struct()
#     data.update({"accuracies": accuracies})

#     ms_config.next_client.ms_comm.send_data(msComm, data, {})

#endregion

# ---  DYNAMOS Interface code At the Bottom --------

def handle_request_async(msComm: msCommTypes.MicroserviceCommunication, request: rabbitTypes.Request):
    if request.type == "vflAggregateRequest":
        handle_vflAggregateRequest(msComm, request)

    elif request.type == "vflPingRequest":
        handle_vflPingRequest(msComm)

    elif request.type == "vflShutdownRequest":
        handle_vflShutdownRequest(msComm)
    
    elif request.type == "vflSampleBatchRequest":
        handle_vflSampleBatchRequest(msComm, request)

    # Obsolete - saving communication
    elif request.type == "vflGetAccuraciesRequest":
        handle_vflGetAccuraciesRequest(msComm)

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
        logger.info(f"Received request: {request.type}. This is the server.")
        thread = threading.Thread(target=handle_request_async, args=(msComm, request,))
        thread.start()

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
