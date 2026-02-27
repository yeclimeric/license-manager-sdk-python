import json
import logging
import threading
import time
from typing import Callable, Optional

import requests
from requests.exceptions import RequestException

from license_manager.config import Config
from license_manager.models import HeartbeatRequest, HeartbeatResponse


class HeartbeatService:
    def __init__(self, cfg: Config):
        base = cfg.server.rstrip("/")
        if cfg.base_path:
            base = f"{base}/{cfg.base_path.strip('/')}"
            
        self.base_url = base
        self.headers = cfg.http_headers or {}
        self.timeout = cfg.http_timeout_or_default()
        
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session.headers.update(self.headers)

    def send(self, req: HeartbeatRequest) -> HeartbeatResponse:
        url = f"{self.base_url}/api/v1/heartbeat"
        payload = req.to_dict()
        
        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
        except RequestException as e:
            raise ValueError(f"heartbeat: network error: {e}")
            
        try:
            resp_data = resp.json()
        except ValueError:
            raise ValueError(f"heartbeat: decode response failed, status {resp.status_code}")
            
        if resp.status_code >= 300:
            if isinstance(resp_data, dict) and "message" in resp_data:
                msg = resp_data.get("message", "")
                code = resp_data.get("code", "")
                raise ValueError(f"heartbeat: {msg} ({code})")
            raise ValueError(f"heartbeat: status {resp.status_code}")
            
        code = resp_data.get("code", "")
        message = resp_data.get("message", "")
        
        if code and str(code) != "000000":
            raise ValueError(f"heartbeat: {message} ({code})")
            
        data = resp_data.get("data")
        if not data:
            raise ValueError("heartbeat: response missing data")
            
        return HeartbeatResponse.from_dict(data)


class HeartbeatManager:
    def __init__(
        self,
        service: HeartbeatService,
        req: HeartbeatRequest,
        interval_seconds: int,
        on_license_updated: Optional[Callable[[HeartbeatResponse], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_ping: Optional[Callable[[], None]] = None
    ):
        self.service = service
        self.req = req
        self.interval = interval_seconds
        self.on_license_updated = on_license_updated
        self.on_error = on_error
        self.on_ping = on_ping
        
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        
        self.running = False
        self.paused = False

    def start(self):
        with self._lock:
            if self.running:
                return
            self.running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            # Don't join immediately to avoid blocking main thread on exit if not needed,
            # or we could join if we want strictly clean shutdowns.
            # self._thread.join(timeout=2)
            pass
            
        with self._lock:
            self.running = False

    def pause(self):
        with self._lock:
            self.paused = True

    def resume(self):
        with self._lock:
            self.paused = False

    def _loop(self):
        try:
            current_interval = self.interval
            while not self._stop_event.is_set():
                # wait using stop_event with a timeout, allowing responsive stopping
                if self._stop_event.wait(current_interval):
                    break
                    
                with self._lock:
                    paused = self.paused
                    
                if paused:
                    continue
                    
                try:
                    resp = self.service.send(self.req)
                    
                    if self.on_ping:
                        threading.Thread(target=self.on_ping, daemon=True).start()
                        
                    if resp.heartbeat_interval and resp.heartbeat_interval > 0:
                        current_interval = resp.heartbeat_interval
                    else:
                        current_interval = self.interval
                        
                    if resp.license_file and self.on_license_updated:
                        # Call callback in a separate thread so we don't block next heartbeat
                        threading.Thread(target=self.on_license_updated, args=(resp,), daemon=True).start()
                        
                except Exception as e:
                    current_interval = self._backoff(current_interval)
                    if self.on_error:
                        threading.Thread(target=self.on_error, args=(e,), daemon=True).start()
        finally:
            with self._lock:
                self.running = False

    def _backoff(self, current: float) -> float:
        nxt = current * 2
        if nxt > 1800:  # 30 minutes max
            nxt = 1800
        if nxt < 30:    # 30 seconds min out of retry
            nxt = 30
        return nxt
