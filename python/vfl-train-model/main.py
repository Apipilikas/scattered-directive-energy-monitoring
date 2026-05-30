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

SERVER_CHECKPOINT_PATH = "server_checkpoint.pth"

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
        self.intermediate_neurons = 4
        self.clients_no = 3

        self._update_model()
        self.criterion = nn.BCELoss()
        self.data = data

        self.accuracies = {}
        self.current_cycle = 0

        self.training_lock = threading.Lock()
        self.training_thread = None

        self.labels = {}
        self.embeddings = {}
        self.communications = {}
        self.embeddings_queue = queue.Queue()
        self.gradients_queue = queue.Queue()

        threading.Thread(target=self._execute_training_process_async).start()
        threading.Thread(target=self._execute_communication_process_async).start()

    def _execute_training_process_async(self):
        while True:
            try:
                cycle = self.embeddings_queue.get_nowait()
                gradients = self.aggregate_fit(cycle)
                self.gradients_queue.put((cycle, gradients))
                self.local_update(cycle, 15)
            except queue.Empty:
                pass

    def _execute_communication_process_async(self):
        while True:
            try:
                cycle, gradients = self.gradients_queue.get_nowait()
                data = Struct()
                logger.debug("Latest gradients have been fetched.")
                data.update({"cycle": cycle})
                data.update({"gradients": gradients})
                data.update({"accuracies": serialise_dictionary(self.accuracies)})
                msComm = self.communications[cycle]
                logger.debug("------------------------------------------")
                ms_config.next_client.ms_comm.send_data(msComm, data, {})
                logger.debug("------------------------------------------")
            except queue.Empty:
                pass

    def put_embeddings(self, cycle, embeddings):

        # new_clients_no = len(embeddings)

        # if new_clients_no != self.clients_no:
        #     logger.info(f"Number of clients {new_clients_no} does not match expected {self.clients_no}, updating server architecture...")
        #     self.update_server_model_architecture(new_clients_no, backtrack)
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
    
    def _update_model(self):
        self.model = ServerModel(self.intermediate_neurons * self.clients_no)
        self.optimizer = optim.SGD(self.model.parameters(), lr=0.01)

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

    def aggregate_fit(self, cycle, backtrack = False):
        logger.info(f"Aggregate fit for cycle {cycle}.")
        global server_configuration

        labels = self.labels[cycle]
        embeddings = self.embeddings[cycle]
        
        with self.training_lock:
            output = self.model(embeddings)
            loss = self.criterion(output, labels)
            
            self.optimizer.zero_grad()
            loss.backward()

        try:
            split_size = [self.intermediate_neurons] * self.clients_no
            gradients = embeddings.grad.split(split_size, dim=1)
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
            logger.debug(f"Accuracies: {self.accuracies}")
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

        cycle, gradients = self.gradients_queue.get_nowait()
        logger.debug("Latest gradients have been fetched.")
        data.update({"cycle": cycle})
        data.update({"gradients": gradients})
        data.update({"accuracies": serialise_dictionary(self.accuracies)})

        return data
    
    def shrink_server_model(self, new_clients_no, backtrack):
        """
        Creates a new ServerModel with fewer input neurons and copies over the trained weights
        from the old model for the first new_input_size neurons.
        """
        if backtrack and new_clients_no==2:  # for now hardcoded to work only when reducing size from 3 to 2 clients
            # save model state to file
            logger.info("Saving server state before shrinking...")
            self.save_state(SERVER_CHECKPOINT_PATH)
        self.clients_no = new_clients_no
        # Create the new model
        # note: this is a completely new model with random weights
        self._update_model()
    
    def expand_server_model(self, new_clients_no, backtrack):
        """
        Creates a new ServerModel with fewer input neurons and copies over the trained weights
        from the old model for the first new_input_size neurons.
        """
        self.clients_no = new_clients_no
        if backtrack and self.clients_no==3:  # for now hardcoded to work only for 3 clients
            # save model state to file
            self._update_model()
            logger.info("Loading previous server state...")
            self.load_state(SERVER_CHECKPOINT_PATH)
        else:
            # Create the new model
            # note: this is a completely new model with random weights
            self._update_model()
    
    def update_server_model_architecture(self, new_clients_no, backtrack):
        if new_clients_no == self.clients_no:
            # No change needed
            logger.debug("Number of clients unchanged, no model architecture update needed.")
        
        if new_clients_no < self.clients_no:
            logger.info(f"Number of clients decreased from {self.clients_no} to {new_clients_no}, shrinking model.")
            self.shrink_server_model(new_clients_no, backtrack)
        
        if new_clients_no > self.clients_no:
            logger.info(f"Number of clients increased from {self.clients_no} to {new_clients_no}, expanding model.")
            self.expand_server_model(new_clients_no, backtrack)

    def save_state(self, filepath):
        """Save the state dicts for both model and optimizer to disk."""
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict()
        }, filepath)
        print(f"Server state saved to {filepath}")

    def load_state(self, filepath):
        """Load the state dicts for both model and optimizer from disk."""
        state = torch.load(filepath)
        self.model.load_state_dict(state['model_state_dict'])
        self.optimizer.load_state_dict(state['optimizer_state_dict'])
        print(f"Server state loaded from {filepath}")

#region Request handlers

def handle_vflAggregateRequest(msComm, request):
    global ms_config
    global vfl_server

    try:
        data = request.data["embeddings"]

        clients_embeddings = [deserialise_array(
            embeddings.string_value
            ) for embeddings in data.list_value.values]
        
        backtrack_flag = int(extract_number_from_data(request, "trainingBacktrack"))
        sample_indexes = extract_array_from_data(request, "sample_batch_indexes")
        communication_frequency = int(extract_number_from_data(request, "communication_frequency"))
        cycle = int(extract_number_from_data(request, "cycle"))

        backtrack = True if backtrack_flag == 1 else False
    except Exception as e:
        logger.error(f"Errored when deserialising client data: {e}")

    # vfl_server.wait_for_training_to_finish()

    # vfl_server.current_cycle = cycle

    vfl_server.communications[cycle] = msComm
    vfl_server.set_labels_from_sample(cycle, sample_indexes)
    vfl_server.put_embeddings(cycle, clients_embeddings)

    # vfl_server.comm = msComm
    # data = vfl_server.get_latest_gradients()

    # ms_config.next_client.ms_comm.send_data(msComm, data, {})

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
        # gradients_data = vfl_server.get_latest_gradients()

        # data.MergeFrom(gradients_data)

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

#endregion

#region DYNAMOS interface

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

#endregion

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
