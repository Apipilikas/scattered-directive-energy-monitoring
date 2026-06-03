from mife.multi.damgard import FeDamgardMulti as MIFE
from mife.single.selective.ddh import FeDDH as SIFE
import numpy as np

def main():
    n = 10
    x = [i for i in range(n)]
    y = [i + 10 for i in range(n)]
    key = SIFE.generate(n)
    print(f"Encrypting: {x}")
    c = SIFE.encrypt(x, key)
    print(f"Generating key with: {y}")
    sk = SIFE.keygen(y, key)
    m = SIFE.decrypt(c, key.get_public_key(), sk, (0, 1000))
    value = np.dot(x, y)
    print(f"The expected value is: {np.sum(value)}")
    print(f"Decrypted: {m}")

if __name__ == "__main__":
    main()