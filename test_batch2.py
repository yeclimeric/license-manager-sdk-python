import base64
import json
import os
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from license_manager.storage import FileStore
from license_manager.validator import Validator


def test_storage():
    test_file = "test_store.lic"
    store = FileStore(test_file, b"super_secret_key_123")
    data = b"hello crypto"
    store.save(data)
    loaded = store.load()
    assert loaded == data
    store.delete()
    print("Storage AES-GCM verified.")


def test_validator():
    # Make a dummy keypair
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    pub_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    val = Validator(pub_pem)

    # create payload
    exp = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    payload_dict = {
        "license_key": "abc",
        "authorization_code": "def",
        "hardware_fingerprint": "finger123",
        "status": "active",
        "start_date": datetime.now(timezone.utc).isoformat(),
        "end_date": exp,
    }
    payload_bytes = json.dumps(payload_dict).encode("utf-8")

    # sign it using PKCS1v15
    sig = private_key.sign(payload_bytes, padding.PKCS1v15(), hashes.SHA256())

    envelope = {
        "algorithm": "RSA-SHA256",
        "data": payload_dict,  # in python json.dumps we need primitive
    }
    # To mimic envelope, Data is a string representing nested json
    envelope = {
        "algorithm": "RSA-SHA256",
        "data": json.dumps(payload_dict),
        "signature": base64.b64encode(sig).decode("utf-8"),
    }

    env_bytes = json.dumps(envelope).encode("utf-8")

    # Verify ok
    p = val.verify(env_bytes, "finger123")
    assert p.license_key == "abc"

    # Verify fingerprint fail
    try:
        val.verify(env_bytes, "wrong_finger")
        assert False
    except ValueError as e:
        assert "mismatch" in str(e)

    print("Validator RSA verified.")


if __name__ == "__main__":
    test_storage()
    test_validator()
