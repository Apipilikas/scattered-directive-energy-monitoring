import pandas as pd
import numpy as np
import sys
import os
import io
import json
from collections import OrderedDict
from sklearn.preprocessing import StandardScaler
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
from sklearn.preprocessing import StandardScaler
from google.protobuf.struct_pb2 import Struct, ListValue, Value
from mife.multi.damgard import FeDamgardMulti as MIFE
from mife.single.selective.ddh import FeDDH as SIFE
from abc import ABC, abstractmethod
import pickle
import base64


np.set_printoptions(threshold=sys.maxsize)

# Variables
DATA_STEWARD_NAME = os.getenv("DATA_STEWARD_NAME", "").lower()

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
vfl_party = None

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
    DATA_STEWARD_NAME = os.getenv("DATA_STEWARD_NAME", "").lower()

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
    # logger.info(f"Raw string: {string} | Encoded data: {encoded_data}")
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

def extract_string_from_data(request: rabbitTypes.Request, property_name: str):
    prop = extract_data(request, property_name)
    
    if (prop != None):
        return prop.string_value
    else:
        return None
    
def extract_array_from_data(request: rabbitTypes.Request, property_name: str):
    prop = extract_string_from_data(request, property_name)
    
    if (prop != None):
        return deserialise_array(prop)
    else:
        return None

def extract_list_from_data(request: rabbitTypes.Request, property_name: str):
    prop = extract_data(request, property_name)
    
    if (prop != None):
        return prop.list_value.values
    else:
        return None

def serialize_crypto_object(key) -> str:
    """Serializes key into a string."""
    raw_bytes = pickle.dumps(key)
    return base64.b64encode(raw_bytes).decode('utf-8')

def deserialize_crypto_object(exported_key: str):
    """Deserializes key into the actual key object."""
    raw_bytes = base64.b64decode(exported_key.encode('utf-8'))
    return pickle.loads(raw_bytes)

#endregion


#region VFL Party classes

class VFLParty(ABC):
    features_scale = 100
    samples_scale = 100

    def __init__(self, data):
        self.data = data
        self.features_size = 0
        self.batch = None
        self.weights = None
        self.mife_sk = None # Encryption key / Secret key / sk_MIFE_pi
        self.sife_pk = None # Encryption key / Public key / pk_SIFE

        self.learning_rate = 0.1

    def set_keys(self, mife_sk, sife_pk):
        self.mife_sk = mife_sk
        self.sife_pk = sife_pk

    def sample_data(self, sample_batch_size):
        data_sample = self.data.sample(int(sample_batch_size))
        return np.array(data_sample.index)

    def get_training_batch(self, sample_indexes):
        batch_sample = self.data.loc[sample_indexes]
        return batch_sample
    
    def set_training_batch(self, sample_indexes):
        self.batch = self.get_training_batch(sample_indexes)

    def update_weights(self, gradients):
        self.weights = self.weights - self.learning_rate * np.array(gradients)
    
    @abstractmethod
    def _update_partial_model(self):
        pass

    def extract_feature_dimension(self):
        updated_model = self._update_partial_model()
        updated_model =  np.array(updated_model).flatten()

        # Up-scaling the data for better precision
        scaled_model = updated_model * self.features_scale
        rounded_model = [int(val) for val in np.round(scaled_model)]

        return MIFE.encrypt(rounded_model, self.mife_sk)

    def extract_sample_dimension(self):
        cts = []
        
        for i in range(self.batch.shape[1]):
            column = self.batch[:, i]
            scaled_column = np.round(column * self.samples_scale)
            lst = scaled_column.astype(int).tolist()
            ct = SIFE.encrypt(lst, self.sife_pk)
            cts.append(ct)

        return cts
    
    def extract_ciphertexts(self):
        ct_fd = self.extract_feature_dimension() # ciphertext for feature dimension SA
        ct_sds = self.extract_sample_dimension() # ciphertext list for sample dimension SA
        return ct_fd, ct_sds

class VFLActiveParty(VFLParty):
    def __init__(self, data):
        super().__init__(data)

    def _update_partial_model(self):
        # Exclude labels from calculation
        return np.zeros(len(self.batch))
        # return -np.array(self.batch) This was for linear regression

    def extract_sample_dimension(self):
        # Server holds labels, so it skips Phase 2 (SIFE)
        return None
    
    def calculate_accuracy(self, decrypted_dimensions_dimension):
        z_raw = np.array(decrypted_dimensions_dimension) / VFLParty.features_scale 
        
        predictions = 1 / (1 + np.exp(-z_raw))

        true_labels = self.batch
        
        logistic_error = predictions - true_labels

        batch_loss = np.mean(np.abs(logistic_error)) 
        correct_predictions = np.sum((predictions >= 0.5) == true_labels)
        batch_accuracy = correct_predictions / len(self.batch)

        return batch_loss, batch_accuracy, logistic_error

class VFLPassiveParty(VFLParty):
    def __init__(self, data):
        super().__init__(data)
        self.scaler = StandardScaler()
        self.scaler.fit(self.data)
        self.features_size = len(self.data.columns)

        self._initialize_weights()

    def _initialize_weights(self):
        self.weights = np.random.randn(self.features_size) * 0.01

    def set_training_batch(self, sample_indexes):
        sample_data = self.get_training_batch(sample_indexes)
        scaled_data = self.scaler.transform(sample_data)
        self.batch = scaled_data

    def _update_partial_model(self):
        return np.dot(self.batch, self.weights)

#endregion

#region Request handlers

def handle_vflShutdownRequest(msComm: msCommTypes.MicroserviceCommunication):
    global ms_config

    ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})
    signal_continuation(stop_event, stop_microservice_condition)

def handle_vflExtractCiphertextsRequest(msComm: msCommTypes.MicroserviceCommunication, 
                                        request: rabbitTypes.Request):
    global ms_config
    global vfl_party

    data = Struct()

    try:
        sample_indexes = extract_array_from_data(request, "sample_batch_indexes")
        vfl_party.set_training_batch(sample_indexes)

        ct_fd, ct_sds = vfl_party.extract_ciphertexts()

        feature_dimension_str = serialize_crypto_object(ct_fd)
        sample_dimension = [serialize_crypto_object(ct_sd) for ct_sd in ct_sds]

        data.update({"feature_dimension": feature_dimension_str})
        data.update({"sample_dimension": sample_dimension})
    except Exception as e:
        logger.error(f"Error occurred while handling vflExtractCiphertextsRequest: {e}")

    ms_config.next_client.ms_comm.send_data(msComm, data, {})

def handle_vflGradientDescentRequest(msComm: msCommTypes.MicroserviceCommunication, 
                                     request: rabbitTypes.Request):
    global ms_config
    global vfl_party

    try:
        gradients = extract_array_from_data(request, "gradients")
        vfl_party.update_weights(gradients)
    except Exception as e:
        logger.error(f"Error occurred while handling vflGradientDescentRequest: {e}")


    ms_config.next_client.ms_comm.send_data(msComm, Struct(), {})

def handle_vflPingRequest(msComm: msCommTypes.MicroserviceCommunication):
    global ms_config
    
    ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})

def handle_vflInitializeRequest(msComm: msCommTypes.MicroserviceCommunication,
                                    request: rabbitTypes.Request):
    try:
        mife_encryption_key_str = extract_string_from_data(request, "mife_encryption_key")
        sife_public_key_str = extract_string_from_data(request, "sife_public_key")

        mife_encryption_key = deserialize_crypto_object(mife_encryption_key_str)
        sife_public_key = deserialize_crypto_object(sife_public_key_str)

        vfl_party.set_keys(mife_encryption_key, sife_public_key)
        logger.debug("Keys have been initialized successfully.")
    except Exception as e:
        logger.error(f"Error occurred while handling vflInitializeRequest: {e}")

    ms_config.next_client.ms_comm.send_data(msComm, Struct(), {})

def handle_vflSampleBatchRequest(msComm: msCommTypes.MicroserviceCommunication,
                                 request: rabbitTypes.Request):
    global ms_config
    global vfl_party

    data = Struct()

    try:
        sample_batch_size = extract_number_from_data(request, "sample_batch_size")

        data_sample = vfl_party.sample_data(sample_batch_size)

        data.update({"sample_batch_indexes": serialise_array(data_sample)})

        ms_config.next_client.ms_comm.send_data(msComm, data, {})
    except Exception as e:
        logger.info(f"Error occurred while handling vflSampleBatchRequest: {e}")

def handle_vflCalculateAccuracyRequest(msComm: msCommTypes.MicroserviceCommunication,
                                       request: rabbitTypes.Request):
    global ms_config
    global vfl_party

    data = Struct()

    try:
        # This is a list[int]
        decrypted_dimensions_dimension = extract_list_from_data(request, "decrypted_dimensions_dimension")

        batch_loss, batch_accuracy, logistic_error = vfl_party.calculate_accuracy(decrypted_dimensions_dimension)

        data.update({"batch_loss": batch_loss})
        data.update({"batch_accuracy": batch_accuracy})
        data.update({"logistic_error": logistic_error})
    except Exception as e:
        logger.info(f"Error occurred while handling vflSampleBatchRequest: {e}")
    
    ms_config.next_client.ms_comm.send_data(msComm, data, {})

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

    if DATA_STEWARD_NAME == "aggregator" or DATA_STEWARD_NAME == "authority":
        if request.type == "vflShutdownRequest":
            handle_vflShutdownRequest(msComm)
        else:
            logger.info("This is the server (not client), relaying request.")
            ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})
    else:
        if request is not None:
            logger.info(f"Received request: {request.type}. This is the client.")
            
            if request.type == "vflInitializeRequest":
                handle_vflInitializeRequest(msComm, request)

            elif request.type == "vflSampleBatchRequest" and isinstance(vfl_party, VFLActiveParty):
                handle_vflSampleBatchRequest(msComm, request)

            elif request.type == "vflExtractCiphertextsRequest":
                handle_vflExtractCiphertextsRequest(msComm, request)
                
            elif request.type == "vflGradientDescentRequest":
                handle_vflGradientDescentRequest(msComm, request)

            elif request.type == "vflCalculateAccuracyRequest" and isinstance(vfl_party, VFLActiveParty):
                handle_vflCalculateAccuracyRequest(msComm, request)

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
    global vfl_party

    try:
        data = load_data(config.dataset_filepath)
        if DATA_STEWARD_NAME == "server":
            vfl_party = VFLActiveParty(data)
        else:
            vfl_party = VFLPassiveParty(data)
            
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

    if ms_config.next_client:
        ms_config.next_client.rabbit.stop()

    ms_config.stop(2)
    logger.debug(f"Exiting {config.service_name}")
    sys.exit(0)

# ---  END DYNAMOS Interface code At the Bottom -----------------


if __name__ == "__main__":
    main()
