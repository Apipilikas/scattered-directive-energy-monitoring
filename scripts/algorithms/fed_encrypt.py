import pandas as pd
import numpy as np
import sys
import os
import io
import json
from collections import OrderedDict
from sklearn.preprocessing import StandardScaler
from google.protobuf.struct_pb2 import Struct, ListValue, Value
from mife.multi.damgard import FeDamgardMulti as MIFE
from mife.single.selective.ddh import FeDDH as SIFE
from abc import ABC, abstractmethod

# The key generator
class VFLAuthority:
    def __init__(self):
        self.clients_size = 4
        self.features_size = 5
        self.batch_size = 256
        self._mife_key = None
        self._sife_key = None
        pass

    # Setup
    def generate_keys(self):
        print(f"Generating mife key with n (clients size): {self.clients_size} and m (batch size): {self.batch_size}.`")
        self._mife_key = MIFE.generate(self.clients_size, self.batch_size)        
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

        data = Struct()
        data.update({"sample_batch_indexes": serialise_array(np.array(data_sample.index))})

        return data

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
        scaled_model = updated_model * self.features_scale
        rounded_model = [int(val) for val in np.round(scaled_model)]
        # print(rounded_model)
        # print(f"Len: {len(rounded_model)}")
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
        # return -np.array(self.batch)

    def extract_sample_dimension(self):
        # Server holds labels, so it skips Phase 2 (SIFE)
        return None

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

class VFLAggregator:
    def __init__(self):
        self.clients_size = 4
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
        return len(v) == self.clients_size

    def check_weighted_features_validity(self, u):
        return len(u) == self.batch_size

    def decrypt_features_dimension(self, ct_fds, dk_v):
        return MIFE.decrypt(ct_fds, self.mife_pk, dk_v, self.mife_bound)
    
    def decrypt_samples_dimension(self, ct_sds, dk_u):
        decs = []

        for ct_sd in ct_sds:
            dec = SIFE.decrypt(ct_sd, self.sife_pk, dk_u, self.sife_bound)
            decs.append(dec)

        return decs


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

    
def main():
    train_datac1 = pd.read_csv('data/train/clientoneData.csv')
    train_datac2 = pd.read_csv('data/train/clienttwoData.csv')
    train_datac3 = pd.read_csv('data/train/clientthreeData.csv')
    train_datas = pd.read_csv('data/train/outcomeData.csv')["Survived"].astype(int)

    test_datac1 = pd.read_csv('data/test/clientoneData.csv').fillna(0)
    test_datac2 = pd.read_csv('data/test/clienttwoData.csv').fillna(0)
    test_datac3 = pd.read_csv('data/test/clientthreeData.csv').fillna(0)
    test_datas = pd.read_csv('data/test/outcomeData.csv')

    features_size = len(train_datac1.columns) + len(train_datac2.columns) + len(train_datac3.columns)

    client1 = VFLPassiveParty(train_datac1)
    client2 = VFLPassiveParty(train_datac2)
    client3 = VFLPassiveParty(train_datac3)
    server = VFLActiveParty(train_datas)

    parties = {
        "clientone": client1,
        "clienttwo": client2,
        "clientthree": client3,
        "server": server
    }

    # Variables
    sample_batch_size = 256
    iterations = 180
    clients_size = len(parties)

    # Initialize Authority
    authority = VFLAuthority()
    authority.clients_size = clients_size
    authority.batch_size = sample_batch_size
    authority.features_size = features_size
    authority.generate_keys()

    # Initialize Aggregator
    aggregator = VFLAggregator()
    aggregator.clients_size = clients_size
    aggregator.batch_size = sample_batch_size
    aggregator.set_public_keys(authority.get_sife_public_key(), authority.get_mife_public_key())
    
    accs = []

    idx = 0
    # Initialization
    for party_id, party in parties.items():
        party.set_keys(authority.get_mife_encryption_key(idx), authority.get_sife_public_key())
        idx += 1

    gradients = []
    for i in range(iterations):
        print(f"----------------------- Run {i + 1} / {iterations} -----------------------")
        sample_indexes = deserialise_array(server.sample_data(sample_batch_size)["sample_batch_indexes"])

        C_fd = {}
        C_sd = {}
        for party_id, party in parties.items():
            # Send aggregator vflGetWeightsRequest
            # Send parties vflExtractCiphertextsRequest (sample_indexes, local_weights)
            party.set_training_batch(sample_indexes)
            
            ct_fd, ct_sds = party.extract_ciphertexts()
            
            C_fd[party_id] = ct_fd
            if ct_sds is not None:
                C_sd[party_id] = ct_sds

        C_fd_ordered = [C_fd["clientone"], C_fd["clienttwo"], C_fd["clientthree"], C_fd["server"]]
        u = []
        
        for k in range(sample_batch_size):
            # Everything is 0, except the k-th column which is 1.
            v_k = [[1 if j == k else 0 for j in range(sample_batch_size)] for _ in range(clients_size)]
            
            # Send authority vflMIFEDKGenRequest
            dk_v_mife_k = authority.generate_mife_decryption_key(v_k)
            
            # Send aggragator vflFeaturesDecRequest
            u_k = aggregator.decrypt_features_dimension(C_fd_ordered, dk_v_mife_k)
            u.append(u_k)

        # Reverse the scaling
        z_raw = np.array(u) / VFLParty.features_scale 
        
        predictions = 1 / (1 + np.exp(-z_raw))
        
        true_labels = server.batch
        
        logistic_error = predictions - true_labels

        batch_loss = np.mean(np.abs(logistic_error)) 
        correct_predictions = np.sum((predictions >= 0.5) == true_labels)
        batch_accuracy = correct_predictions / sample_batch_size
        
        print(f"> Loss: {batch_loss:.4f} | Accuracy: {batch_accuracy * 100:.2f}%")
        
        accs.append(batch_accuracy)

        u = [int(val) for val in np.round(logistic_error * 100.0)]

        # Send authority vflSIFEDKGenRequest
        dk_u_sife = authority.generate_sife_decryption_key(u)

        gradients = {}

        for party_id, ct_sds in C_sd.items():
            # Send aggragator vflSampleDecRequest
            party_gradients = aggregator.decrypt_samples_dimension(ct_sds, dk_u_sife)
            float_gradients = [g / (VFLParty.features_scale * VFLParty.samples_scale * sample_batch_size) for g in party_gradients]
            gradients[party_id] = float_gradients

            # Send vflGradientDescentRequest
            parties[party_id].update_weights(float_gradients)
    
    print("------------------------------------------")
    print("Intermediate accuracies:")
    print(accs)
    print("------------------------------------------")

    # > Test the model
    test_size = len(test_datac1)
    scaled_test = client1.scaler.transform(test_datac1[client1.data.columns])
    client1.batch = scaled_test
    scaled_test = client2.scaler.transform(test_datac2[client2.data.columns])
    client2.batch = scaled_test
    scaled_test = client3.scaler.transform(test_datac3[client3.data.columns])
    client3.batch = scaled_test

    server.batch = np.zeros(test_size)

    authority_test = VFLAuthority()
    authority_test.clients_size = clients_size
    authority_test.batch_size = test_size
    authority_test.generate_keys()

    # Distribute the Inference Keys to the clients and aggregator
    idx = 0
    for party_id, party in parties.items():
        party.set_keys(authority_test.get_mife_encryption_key(idx), authority_test.get_sife_public_key())
        idx += 1
    aggregator.batch_size = test_size
    aggregator.mife_pk = authority_test.get_mife_public_key()

    C_fd_test = {}
    C_sd_test = {}
    for party_id, party in parties.items():
        # Send aggregator vflGetWeightsRequest
        # Send parties vflExtractCiphertextsRequest (sample_indexes, local_weights)
        # party.set_training_batch(sample_indexes)
            
        ct_fd, ct_sds = party.extract_ciphertexts()
            
        C_fd_test[party_id] = ct_fd
        if C_sd_test is not None:
            C_sd_test[party_id] = ct_sds

    C_fd_ordered_test = [C_fd_test["clientone"], C_fd_test["clienttwo"], C_fd_test["clientthree"], C_fd_test["server"]]

    u_test = []
        
    for k in range(test_size):
        # Everything is 0, except the k-th column which is 1.
        v_k = [[1 if j == k else 0 for j in range(test_size)] for _ in range(clients_size)]
        
        # Send authority vflMIFEDKGenRequest
        dk_v_mife_k = authority_test.generate_mife_decryption_key(v_k)
        
        # Send aggragator vflFeaturesDecRequest
        u_k = aggregator.decrypt_features_dimension(C_fd_ordered_test, dk_v_mife_k)
        u_test.append(u_k)

    test_z_raw = np.array(u_test) / 100.0
    test_probabilities = 1 / (1 + np.exp(-test_z_raw))

    survived_predictions = (test_probabilities >= 0.5).astype(int)

    passenger_ids = test_datas["PassengerId"].values
                
    train_df = pd.DataFrame({
        "PassengerId": passenger_ids,
        "Survived": survived_predictions
    })

    train_df.to_csv("data/testData.csv", index=False)


if __name__ == "__main__":
    main()