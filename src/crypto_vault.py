"""
crypto_vault.py — IBM Z Secure Execution simulator using AES-256-CBC.

Simulates the IBM Z Trusted Execution Environment (TEE) concept:
- Data is encrypted at rest with AES-256-CBC.
- The key never leaves the vault object (analogous to hardware-protected keys in IBM Z SE).
- decrypt_for_model() is the only way to get plaintext — simulating data flowing
  inside the TEE without being exposed to the outside world.
- make_scrambled_view() produces the "Screen A" hex gibberish that banks/admins see.
"""

import io
import os
import secrets

import pandas as pd
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

# Output paths — resolved relative to this file's parent (project root)
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
ENCRYPTED_PATH = os.path.join(DATA_DIR, "encrypted_transactions.bin")
SCRAMBLED_PATH = os.path.join(DATA_DIR, "scrambled_view.csv")


class SecureVault:
    """
    Simulates IBM Z Secure Execution: AES-256-CBC encrypted storage.

    The _key and _iv are generated once at construction and kept private.
    All encryption/decryption operations use these stored secrets — they
    are never returned to the caller.
    """

    def __init__(self):
        # 32 bytes → AES-256; 16 bytes → CBC IV
        self._key: bytes = secrets.token_bytes(32)
        self._iv: bytes = secrets.token_bytes(16)
        os.makedirs(DATA_DIR, exist_ok=True)

    def _pad(self, data: bytes) -> bytes:
        """Apply PKCS7 padding to make data block-aligned (16-byte blocks)."""
        padder = padding.PKCS7(128).padder()
        return padder.update(data) + padder.finalize()

    def _unpad(self, data: bytes) -> bytes:
        """Strip PKCS7 padding after decryption."""
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(data) + unpadder.finalize()

    def encrypt(self, df: pd.DataFrame) -> None:
        """
        Serialize df to CSV bytes, encrypt with AES-256-CBC, write
        iv + ciphertext to data/encrypted_transactions.bin.

        The IV is prepended to the ciphertext so decrypt_for_model()
        can read it back without needing an out-of-band channel
        (acceptable in this simulation; in real IBM Z SE, the IV is
        also hardware-protected).
        """
        # Serialize DataFrame to CSV bytes
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        plaintext = buf.getvalue().encode("utf-8")

        # Pad to AES block boundary
        padded = self._pad(plaintext)

        # Encrypt with stored key + IV
        cipher = Cipher(algorithms.AES(self._key), modes.CBC(self._iv))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded) + encryptor.finalize()

        # Write IV prepended to ciphertext so decrypt can extract it
        with open(ENCRYPTED_PATH, "wb") as f:
            f.write(self._iv + ciphertext)

        print(f"🔒 Encrypted {len(plaintext):,} bytes → {ENCRYPTED_PATH}")
        print(f"   (Simulating IBM Z Secure Execution — key never leaves the vault)")

    def decrypt_for_model(self) -> pd.DataFrame:
        """
        Read encrypted_transactions.bin, decrypt with stored key,
        return the original DataFrame.

        Simulates data flowing inside the TEE: the fraud model sees
        plaintext, but no human admin or external process ever does.
        """
        with open(ENCRYPTED_PATH, "rb") as f:
            blob = f.read()

        # First 16 bytes are the IV we wrote during encrypt()
        iv = blob[:16]
        ciphertext = blob[16:]

        cipher = Cipher(algorithms.AES(self._key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        plaintext = self._unpad(padded_plaintext).decode("utf-8")
        df = pd.read_csv(io.StringIO(plaintext))
        return df

    def make_scrambled_view(self, df: pd.DataFrame) -> None:
        """
        Create a 'Screen A' CSV where every data cell is replaced with
        a random 8-character hex string (e.g. 'a3f2c901').

        Column headers are preserved so the table shape remains visible.
        This is what bank admins and screen observers see — pure gibberish.
        """
        scrambled = df.copy()
        for col in scrambled.columns:
            scrambled[col] = [secrets.token_hex(4) for _ in range(len(scrambled))]

        scrambled.to_csv(SCRAMBLED_PATH, index=False)
        print(f"🔀 Scrambled view written → {SCRAMBLED_PATH}")
        print(f"   (Screen A: {len(scrambled)} rows of hex gibberish — customer data fully hidden)")


# ── Convenience runner ───────────────────────────────────────────────────────
if __name__ == "__main__":
    df = pd.read_csv(os.path.join(DATA_DIR, "raw_transactions.csv"))
    vault = SecureVault()
    vault.encrypt(df)
    df2 = vault.decrypt_for_model()
    vault.make_scrambled_view(df)
    assert df2.shape == df.shape, f"Shape mismatch: {df2.shape} vs {df.shape}"
    print(f"✅ Vault round-trip OK — shapes match: {df.shape}")
