from mife.multi.damgard import FeDamgardMulti as MIFE
from mife.single.selective.ddh import FeDDH as SIFE
import numpy as np
import pickle
import base64
import json

def serialize_crypto_object(key) -> str:
    """Serializes key into a string."""
    raw_bytes = pickle.dumps(key)
    return base64.b64encode(raw_bytes).decode('utf-8')

def deserialize_crypto_object(exported_key: str):
    """Deserializes key into the actual key object."""
    raw_bytes = base64.b64decode(exported_key.encode('utf-8'))
    return pickle.loads(raw_bytes)

def serialise_array(array):
    return json.dumps([
        str(array.dtype),
        array.tobytes().decode("latin1"),
        array.shape])

def main():
    n = 10
    x = [i for i in range(n)]
    y = [i + 10 for i in range(n)]
    key = SIFE.generate(n)
    print(f"Encrypting: {x}")
    c = SIFE.encrypt(x, key)
    print(f"Generating key with: {y}")
    sk = SIFE.keygen(y, key)

    exported = serialize_crypto_object(key)
    print(f"Exported key: {exported}")
    s = deserialize_crypto_object(exported)
    print(f"Rebuild key: {s}")

    exported = serialize_crypto_object(sk)
    print(f"Exported key: {exported}")
    skk = deserialize_crypto_object(exported)
    print(f"Rebuild key: {skk}")

    lst = [skk, skk]
    lst_str = serialise_array(lst)

    m = SIFE.decrypt(c, s.get_public_key(), skk, (0, 1000))
    value = np.dot(x, y)
    print(f"The expected value is: {np.sum(value)}")
    print(f"Decrypted: {m}")

if __name__ == "__main__":
    main()