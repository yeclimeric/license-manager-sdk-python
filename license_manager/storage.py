import base64
import hashlib
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class Store:
    def save(self, data: bytes) -> None:
        raise NotImplementedError

    def load(self) -> Optional[bytes]:
        raise NotImplementedError

    def delete(self) -> None:
        raise NotImplementedError


class FileStore(Store):
    def __init__(self, path: str, secret: bytes = b""):
        self.path = path
        self.secret = secret

    def save(self, data: bytes) -> None:
        payload = self._maybe_encrypt(data)

        dir_name = os.path.dirname(self.path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        tmp_path = self.path + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(payload)

        os.replace(tmp_path, self.path)

    def load(self) -> Optional[bytes]:
        if not os.path.exists(self.path):
            return None

        try:
            with open(self.path, "rb") as f:
                content = f.read()
        except Exception:
            return None

        return self._maybe_decrypt(content)

    def delete(self) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)

    def _maybe_encrypt(self, data: bytes) -> bytes:
        if not self.secret:
            return data

        key = hashlib.sha256(self.secret).digest()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)

        ciphertext = aesgcm.encrypt(nonce, data, None)
        # Store as `nonce + ciphertext` in base64 with "enc:" prefix
        buf = b"enc:" + base64.b64encode(nonce + ciphertext)
        return buf

    def _maybe_decrypt(self, data: bytes) -> bytes:
        if not self.secret:
            return data

        prefix = b"enc:"
        if data.startswith(prefix):
            data = data[len(prefix) :]
        else:
            return data

        raw = base64.b64decode(data)
        key = hashlib.sha256(self.secret).digest()
        aesgcm = AESGCM(key)

        nonce = raw[:12]
        payload = raw[12:]

        try:
            return aesgcm.decrypt(nonce, payload, None)
        except Exception as e:
            raise ValueError(f"storage: decrypt: {e}")
