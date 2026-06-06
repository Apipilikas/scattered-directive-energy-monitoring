from mife.multi.damgard import FeDamgardMulti as MIFE
from mife.single.selective.ddh import FeDDH as SIFE
import numpy as np
import dill
import base64
import json

def serialize_crypto_object(key) -> str:
    """Serializes key into a string."""
    raw_bytes = dill.dumps(key)
    return base64.b64encode(raw_bytes).decode('utf-8')

def deserialize_crypto_object(exported_key: str):
    """Deserializes key into the actual key object."""
    raw_bytes = base64.b64decode(exported_key.encode('utf-8'))
    return dill.loads(raw_bytes)

def sife_example():
    print("======== SIFE example ========")
    m = 10
    x = [i for i in range(m)]
    y = [i + 10 for i in range(m)]
    key = SIFE.generate(m)
    print(f"Encrypting: {x}")
    c = SIFE.encrypt(x, key)
    print(f"Generating key with: {y}")
    sk = SIFE.keygen(y, key)

    print(f"Key: {key}")
    exported = serialize_crypto_object(key)
    # print(f"Exported key: {exported}")
    s = deserialize_crypto_object(exported)
    print(f"Deserialized key: {s}")

    print(f"Key: {sk}")
    exported = serialize_crypto_object(sk)
    # print(f"Exported key: {exported}")
    skk = deserialize_crypto_object(exported)
    print(f"Deserialized key: {skk}")

    m = SIFE.decrypt(c, s.get_public_key(), skk, (0, 1000))
    value = np.dot(x, y)
    print(f"The expected value is: {np.sum(value)}")
    print(f"Decrypted: {m}")

def mife_example():
    print("======== MIFE example ========")

    n = 3
    m = 10
    x = [[i + j for j in range(m)] for i in range(n)]
    y = [[i - j + 10 for j in range(m)] for i in range(n)]
    key = MIFE.generate(n, m)
    print(f"Encrypting: {x}")
    cs = [MIFE.encrypt(x[i], key.get_enc_key(i)) for i in range(n)]
    print(f"Generating key with: {y}")
    sk = MIFE.keygen(y, key)

    print(f"Key: {key}")
    exported = serialize_crypto_object(key)
    # print(f"Exported key: {exported}")
    s = deserialize_crypto_object(exported)
    print(f"Deserialized key: {s}")

    print(f"Key: {sk}")
    exported = serialize_crypto_object(sk)
    # print(f"Exported key: {exported}")
    skk = deserialize_crypto_object(exported)
    print(f"Deserialized key: {skk}")

    m = MIFE.decrypt(cs, key.get_public_key(), sk, (0, 2000))
    x_arr = np.array(x)
    y_arr = np.array(y)
    value = np.sum(x_arr * y_arr)
    print(f"The expected value is: {np.sum(value)}")
    print(f"Decrypted: {m}")
def main():
    # sife_example()
    mife_example()
    

if __name__ == "__main__":
    main()