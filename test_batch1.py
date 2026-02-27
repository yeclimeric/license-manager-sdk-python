from license_manager.models import LicensePayload
from license_manager.config import Config
from license_manager.hardware import DefaultHardwareProvider
import json

def test_models():
    data = {
        "license_key": "123",
        "authorization_code": "abc",
        "hardware_fingerprint": "xyz",
        "status": "active",
        "start_date": "2023-01-01T00:00:00Z",
        "end_date": "2024-01-01T00:00:00Z",
    }
    payload = LicensePayload.from_dict(data)
    assert payload.license_key == "123"
    assert payload.expires_at == payload.end_date
    print("Models verified.")

def test_config():
    valid_cfg = Config(product="A", version="1", server="http://a", authorization_code="x")
    valid_cfg.validate()
    print("Config verified.")

def test_hardware():
    hw = DefaultHardwareProvider(["mac", "hostname", "cpu", "memory"])
    fp, details = hw.fingerprint()
    assert fp is not None
    assert type(details) is dict
    print(f"Hardware verified: fp={fp}, details={json.dumps(details)}")

if __name__ == "__main__":
    test_models()
    test_config()
    test_hardware()
