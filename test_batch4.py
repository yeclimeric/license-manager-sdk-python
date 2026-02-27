from license_manager.client import Client, ClientOptions, Callbacks
from license_manager.config import Config
from license_manager.hardware import DefaultHardwareProvider
from license_manager.storage import FileStore
import os

def test_client_init_offline():
    cfg = Config(product="A", version="1", offline=True)
    try:
        cfg.public_key_pem = b"dummy"
        cfg.license_file_path = "dummy.lic"
        # Since it's offline and dummy.lic doesn't exist, it should raise
        client = Client(cfg)
        assert False, "Should raise offline load error"
    except ValueError as e:
        assert "offline mode requires preloaded license" in str(e) or "read public key" in str(e)
        print(f"Caught expected error: {e}")

if __name__ == "__main__":
    test_client_init_offline()
    print("Client integration test verified basic offline fail fast.")
