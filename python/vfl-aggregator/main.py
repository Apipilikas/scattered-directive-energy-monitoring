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
vfl_aggregator = None
vfl_authority = None

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
    raw_bytes = pickle.dumps(key)
    return base64.b64encode(raw_bytes).decode('utf-8')

def deserialize_crypto_object(exported_key: str):
    """Deserializes key into the actual key object."""
    raw_bytes = base64.b64decode(exported_key.encode('utf-8'))
    return pickle.loads(raw_bytes)

#endregion

#region VFL Aggregator class

class VFLAggregator:
    def __init__(self):
        self.parties_size = 4
        self.features_size = 5
        self.batch_size = 256
        self.learning_rate = 0.001
        self.sife_pk = None
        self.mife_pk = None

        self.mife_bound = (-50000, 50000)
        # self.sife_bound = (-50000, 50000)
        self.sife_bound = (-10000000, 10000000)


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

#region VFL Authority class

class VFLAuthority:
    def __init__(self):
        self.parties_size = 0
        self.batch_size = 0
        self._mife_key = None
        self._sife_key = None
        pass

    # Setup
    def generate_keys(self):
        print(f"Generating mife key with n (parties size): {self.parties_size} and m (batch size): {self.batch_size}.`")
        self._mife_key = MIFE.generate(self.parties_size, self.batch_size)        
        print(f"Generating sife key with m (batch size): {self.batch_size}.")
        self._sife_key = SIFE.generate(self.batch_size)
        
    def get_mife_public_key(self):
        return self._mife_key.get_public_key()
    
    # pk_SIFE
    def get_sife_public_key(self):
        return self._sife_key.get_public_key()

    # Or secret key / sk_MIFE_pi
    def get_mife_encryption_key(self, party_id):
        return self._mife_key.get_enc_key(party_id)
    
    # dk_gen mife
    def generate_mife_decryption_key(self, y):
        return MIFE.keygen(y, self._mife_key)

    # dk_gen sife
    def generate_sife_decryption_key(self, y):
        return SIFE.keygen(y, self._sife_key)

#endregion

#region Request handlers

def handle_vflInitializeAggregatorRequest(msComm, request):
    global ms_config
    global vfl_aggregator

    try:
        parties_size = extract_number_from_data(request, "parties_size")
        batch_size = extract_number_from_data(request, "batch_size")

        vfl_aggregator.parties_size = parties_size
        vfl_aggregator.batch_size = batch_size

        mife_public_key_str = extract_string_from_data(request, "mife_public_key")
        sife_public_key_str = extract_string_from_data(request, "sife_public_key")

        mife_public_key = deserialize_crypto_object(mife_public_key_str)
        sife_public_key = deserialize_crypto_object(sife_public_key_str)

        vfl_aggregator.mife_pk = mife_public_key
        vfl_aggregator.sife_pk = sife_public_key
    except Exception as e:
        logger.error(f"Errored when deserialising client data: {e}")

    ms_config.next_client.ms_comm.send_data(msComm, Struct(), {})

def handle_vflShutdownRequest(msComm):
    global ms_config

    logger.info("Received vflShutdownRequest, shutting down service.")
    ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})
    signal_continuation(stop_event, stop_microservice_condition)

def handle_vflPingRequest(msComm):
    logger.info("Received a vflPingRequest.")
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
        C_fd = [deserialize_crypto_object(ct_fd) for ct_fd in encrypted_features_dimension]

        u = []

        for dk_v_mife_str in dks_features_mife:
            dk_v_mife = deserialize_crypto_object(dk_v_mife_str)

            u_k = vfl_aggregator.decrypt_features_dimension(C_fd, dk_v_mife)
            u.append(u_k)

        data.update({"decrypted_features_dimension": u})
    except Exception as e:
        logger.info(f"Error occurred while handling vflSampleBatchRequest: {e}")
    
    ms_config.next_client.ms_comm.send_data(msComm, data, {})

def handle_vflSamplesDecryptionRequest(msComm, request):
    global ms_config
    global vfl_aggregator

    data = Struct()

    try:
        dk_samples_sife_str = extract_string_from_data(request, "dk_samples_sife")
        encrypted_samples_dimension = extract_list_from_data(request, "encrypted_samples_dimension")
        
        dk_u_sife = deserialize_crypto_object(dk_samples_sife_str)

        gradients = []

        for ct_sds in encrypted_samples_dimension:
            party_gradients = vfl_aggregator.decrypt_samples_dimension(ct_sds, dk_u_sife)
            gradients.append(party_gradients)
        
        data.update({"gradients": gradients})
    except Exception as e:
        logger.error(f"Error occurred while handling vflGetAccuraciesRequest: {e}")
    
    ms_config.next_client.ms_comm.send_data(msComm, data, {})

# Authority handlers

def handle_vflInitializeAuthorityRequest(msComm, request):
    global ms_config
    global vfl_authority

    data = Struct()

    try:
        parties_size = extract_number_from_data(request, "parties_size")
        batch_size = extract_number_from_data(request, "batch_size")

        vfl_authority.parties_size = parties_size
        vfl_authority.batch_size = batch_size

        vfl_authority.generate_keys()

        sife_public_key_str = serialize_crypto_object(vfl_authority.get_sife_public_key())
        mife_public_key_str = serialize_crypto_object(vfl_authority.get_mife_public_key())

        mife_encryption_keys = [serialize_crypto_object(vfl_authority.get_mife_encryption_key(i)) 
                                for i in range(vfl_authority.parties_size)]

        data.update({"sife_public_key": sife_public_key_str})
        data.update({"mife_public_key": mife_public_key_str})
        data.update({"mife_encryption_keys": mife_encryption_keys})
    except Exception as e:
        logger.info(f"Error occurred while handling vflSampleBatchRequest: {e}")

    ms_config.next_client.ms_comm.send_data(msComm, data, {})

def handle_vflMIFEDKGenerationRequest(msComm, request):
    global ms_config
    global vfl_authority

    data = Struct()
    dks_v_mife = []

    try:
        for k in range(vfl_authority.batch_size):
            # Everything is 0, except the k-th column which is 1.
            v_k = [[1 if j == k else 0 for j in range(vfl_authority.batch_size)] for _ in range(vfl_authority.parties_size)]

            dk_v_mife_k = vfl_authority.generate_mife_decryption_key(v_k)
            dks_v_mife.append(serialize_crypto_object(dk_v_mife_k))

        data.update({"dks_features_mife": dks_v_mife})
    except Exception as e:
        logger.info(f"Error occurred while handling vflMIFEDKGenerationRequest: {e}")

    ms_config.next_client.ms_comm.send_data(msComm, data, {})

def handle_vflSIFEDKGenerationRequest(msComm, request):
    global ms_config
    global vfl_authority

    data = Struct()

    try:
        logistic_error = extract_list_from_data(request, "logistic_error")

        u = [int(val) for val in np.round(logistic_error * 100.0)]

        dk_u_sife = vfl_authority.generate_sife_decryption_key(u)
        
        data.update({"dk_samples_sife": serialize_crypto_object(dk_u_sife)})
    except Exception as e:
        logger.error(f"Error occurred while handling vflGetAccuraciesRequest: {e}")
    
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

    if DATA_STEWARD_NAME not in ["aggregator", "authority"]:
        if request.type == "vflShutdownRequest":
            handle_vflShutdownRequest(msComm)
        else:
            logger.info(f"Received request: {request.type}. This is the aggregator, relaying request.")
            ms_config.next_client.ms_comm.send_data(msComm, msComm.data, {})

    else:
        logger.info(f"Received request: {request.type}. This is the aggregator.")
        if DATA_STEWARD_NAME == "aggregator" and request.type == "vflInitializeRequest":
            handle_vflInitializeAggregatorRequest(msComm, request)

        elif request.type == "vflPingRequest":
            handle_vflPingRequest(msComm)

        elif request.type == "vflShutdownRequest":
            handle_vflShutdownRequest(msComm)
        
        elif request.type == "vflFeaturesDecryptionRequest":
            handle_vflFeaturesDecryptionRequest(msComm, request)

        elif request.type == "vflSamplesDecryptionRequest":
            handle_vflSamplesDecryptionRequest(msComm, request)

        # Authority requests

        elif DATA_STEWARD_NAME == "authority" and request.type == "vflInitializeRequest":
            handle_vflInitializeAuthorityRequest(msComm, request)

        elif request.type == "vflMIFEDKGenerationRequest":
            handle_vflMIFEDKGenerationRequest(msComm, request)

        elif request.type == "vflSIFEDKGenerationRequest":
            handle_vflSIFEDKGenerationRequest(msComm, request)

        else:
            logger.error(f"An unknown request_type: {msComm.data.type}")

    return Empty()

#endregion

def main():
    global config
    global ms_config
    global vfl_aggregator
    global vfl_authority

    # Aggregator and authority should be on two seperate services. For some reason, when we deploy three services
    # the pods are terminating instantly. No error shown and the exit code is supposed to be 1. We try to distinct
    # the two services so that the future seperation whould be quite easy.

    if DATA_STEWARD_NAME == "aggregator":
        vfl_aggregator = VFLAggregator()
    elif DATA_STEWARD_NAME == "authority":
        vfl_authority = VFLAuthority()

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
