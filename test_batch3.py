import threading
import time
from license_manager.models import HeartbeatRequest, HeartbeatResponse
from license_manager.heartbeat import HeartbeatManager

# Mock service for testing
class MockHeartbeatService:
    def __init__(self):
        self.call_count = 0
        
    def send(self, req: HeartbeatRequest) -> HeartbeatResponse:
        self.call_count += 1
        # alternate failing and success
        if self.call_count % 2 == 0:
            raise ValueError("mock network error")
        return HeartbeatResponse(status="ok", heartbeat_interval=1)

def test_heartbeat_manager():
    service = MockHeartbeatService()
    req = HeartbeatRequest(license_key="test", hardware_fingerprint="fp")
    
    cb_calls = []
    err_calls = []
    
    def on_update(resp):
        cb_calls.append(resp)
        
    def on_error(err):
        err_calls.append(err)
        
    mgr = HeartbeatManager(service, req, interval_seconds=1, on_license_updated=on_update, on_error=on_error)
    mgr.start()
    
    # let it run for 2.5 seconds. Should make ~2 calls.
    time.sleep(2.5)
    mgr.pause()
    time.sleep(1.5) # Shouldn't make calls while paused
    
    mgr.stop()
    
    assert service.call_count > 0, "Should have made calls"
    assert len(err_calls) > 0, "Should have received errors based on mock"
    
    print("Heartbeat manager verified.")

if __name__ == "__main__":
    test_heartbeat_manager()
