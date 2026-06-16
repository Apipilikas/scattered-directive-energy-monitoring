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
import dill
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
vfl_aggregator = None

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
    DATA_STEWARD_NAME = os.getenv("DATA_STEWARD_NAME", "").lower()

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
    raw_bytes = dill.dumps(key)
    return base64.b64encode(raw_bytes).decode('utf-8')

def deserialize_crypto_object(exported_key: str):
    """Deserializes key into the actual key object."""
    raw_bytes = base64.b64decode(exported_key.encode('utf-8'))
    return dill.loads(raw_bytes)

#endregion

#region VFL Aggregator class

class VFLAggregator:
    def __init__(self):
        self.parties_size = 0
        self.features_size = 0
        self.batch_size = 256
        self.learning_rate = 0.1
        self.sife_pk = None
        self.mife_pk = None
        self.weights = []
        self.parties = []

        self.mife_bound = (-50000, 50000)
        # self.sife_bound = (-50000, 50000)
        self.sife_bound = (-10000000, 10000000)

        self.features_scale = 100
        self.samples_scale = 100

    def update_parties(self, parties_features):
        new_parties_order = []
        new_parties = {}

        for party in parties_features.list_value.values:
            item = party.struct_value

            party_id = item.fields["party_id"].string_value
            features_size = int(item.fields["features_size"].number_value)

            new_parties[party_id] = features_size
            new_parties_order.append(party_id)

        old_weights = dict(zip(self.parties, self.weights))

        new_weights = []
        for party_id in new_parties_order:
            if party_id in old_weights:
                # Party exists
                new_weights.append(old_weights[party_id])
            else:
                # New party
                features_size = new_parties[party_id]
                
                new_weight = self._initialize_weights(features_size)
                new_weights.append(new_weight)

        logger.info(f"Old parties: {self.parties}")
        self.parties = new_parties_order
        self.weights = new_weights
        logger.info(f"Updated parties: {new_parties_order}")

    def _initialize_weights(self, features_size):
        return np.random.randn(features_size) * 0.01
    
    def update_weights(self, gradients):
        for i in range(len(self.weights)):
            float_gradients = [g / (self.features_scale * self.samples_scale * self.batch_size) for g in gradients[i]]
            self.weights[i] = self.weights[i] - self.learning_rate * np.array(float_gradients)

    def set_public_keys(self, sife_pk, mife_pk):
        self.sife_pk = sife_pk
        self.mife_pk = mife_pk

    def generate_sample_seed(self):
        return 42

    def check_responding_parties_validity(self, v):
        return len(v) == self.parties_size

    def check_weighted_features_validity(self, u):
        return len(u) == self.batch_size

    def decrypt_features_dimension(self, ct_fds, dk_v):
        return MIFE.decrypt(ct_fds, self.mife_pk, dk_v, self.mife_bound)
    
    def decrypt_samples_dimension(self, ct_sds, dk_u) -> list[int]:
        decs = []

        for ct_sd in ct_sds:
            dec = SIFE.decrypt(ct_sd, self.sife_pk, dk_u, self.sife_bound)
            decs.append(dec)

        return decs

#endregion

#region Request handlers

def handle_vflInitializeRequest(msComm, request):
    global ms_config
    global vfl_aggregator

    data = Struct()

    try:
        parties_size = extract_number_from_data(request, "parties_size")
        batch_size = extract_number_from_data(request, "batch_size")

        vfl_aggregator.parties_size = int(parties_size)
        vfl_aggregator.batch_size = int(batch_size)

        mife_public_key_str = extract_string_from_data(request, "mife_public_key")
        sife_public_key_str = extract_string_from_data(request, "sife_public_key")

        mife_public_key = deserialize_crypto_object(mife_public_key_str)
        sife_public_key = deserialize_crypto_object(sife_public_key_str)

        vfl_aggregator.mife_pk = mife_public_key
        vfl_aggregator.sife_pk = sife_public_key

        parties_features = extract_data(request, "parties_features")
        vfl_aggregator.update_parties(parties_features)

        weights = [serialise_array(w) for w in vfl_aggregator.weights]
        data.update({"weights": weights})
    except Exception as e:
        logger.exception(f"Error occurred while handling handle_vflInitializeRequest: {e}")

    ms_config.next_client.ms_comm.send_data(msComm, data, {})

def handle_vflShutdownRequest(msComm):
    global ms_config

    ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})
    signal_continuation(stop_event, stop_microservice_condition)

def handle_vflPingRequest(msComm):
    ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})

def handle_vflFeaturesDecryptionRequest(msComm, request):
    global ms_config
    global vfl_aggregator

    data = Struct()

    try:
        # Array of strings
        dks_features_mife = extract_list_from_data(request, "dks_features_mife")
        # Array of encrypted key
        encrypted_features_dimension = extract_list_from_data(request, "encrypted_features_dimension")
        C_fd = [deserialize_crypto_object(ct_fd.string_value) for ct_fd in encrypted_features_dimension]

        u = []

        for dk_v_mife_str in dks_features_mife:
            dk_v_mife = deserialize_crypto_object(dk_v_mife_str.string_value)

            u_k = vfl_aggregator.decrypt_features_dimension(C_fd, dk_v_mife)
            u.append(u_k)

        data.update({"decrypted_features_dimension": u})
    except Exception as e:
        logger.exception(f"Error occurred while handling vflFeaturesDecryptionRequest: {e}")
    
    ms_config.next_client.ms_comm.send_data(msComm, data, {})

def handle_vflSamplesDecryptionRequest(msComm, request):
    global ms_config
    global vfl_aggregator

    data = Struct()

    try:
        dk_samples_sife_str = extract_string_from_data(request, "dk_samples_sife")
        encrypted_samples_dimension = extract_list_from_data(request, "encrypted_samples_dimension")
        C_sd = [ct_sds.list_value.values for ct_sds in encrypted_samples_dimension]

        dk_u_sife = deserialize_crypto_object(dk_samples_sife_str)

        gradients = []

        for ct_sds in C_sd:
            ct_sds = [deserialize_crypto_object(ct_sd.string_value) for ct_sd in ct_sds]
            party_gradients = vfl_aggregator.decrypt_samples_dimension(ct_sds, dk_u_sife)
            gradients.append(party_gradients)
        
        vfl_aggregator.update_weights(gradients)
        weights = [serialise_array(w) for w in vfl_aggregator.weights]

        data.update({"weights": weights})
    except Exception as e:
        logger.exception(f"Error occurred while handling vflSamplesDecryptionRequest: {e}")
    
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

    if DATA_STEWARD_NAME != "aggregator":
        if request.type == "vflShutdownRequest":
            handle_vflShutdownRequest(msComm)
        else:
            logger.info(f"Received request: {request.type}. This is the aggregator, relaying request.")
            ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})

    else:
        logger.info(f"Received request: {request.type}. This is the aggregator.")
        if request.type == "vflInitializeRequest":
            handle_vflInitializeRequest(msComm, request)

        elif request.type == "vflPingRequest":
            handle_vflPingRequest(msComm)

        elif request.type == "vflShutdownRequest":
            handle_vflShutdownRequest(msComm)
        
        elif request.type == "vflFeaturesDecryptionRequest":
            handle_vflFeaturesDecryptionRequest(msComm, request)

        elif request.type == "vflSamplesDecryptionRequest":
            handle_vflSamplesDecryptionRequest(msComm, request)

        else:
            logger.error(f"An unknown request_type: {msComm.data.type}")

    return Empty()

#endregion

def main():
    global config
    global ms_config
    global vfl_aggregator

    vfl_aggregator = VFLAggregator()

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

    if ms_config.next_client:
        ms_config.next_client.rabbit.stop()

    ms_config.stop(2)
    logger.debug(f"Exiting {config.service_name}")
    sys.exit(0)

# ---  END DYNAMOS Interface code At the Bottom -----------------


if __name__ == "__main__":
    main()
