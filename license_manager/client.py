import base64
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from license_manager.activation import ActivationService
from license_manager.config import Config
from license_manager.hardware import DefaultHardwareProvider, HardwareProvider
from license_manager.heartbeat import HeartbeatManager, HeartbeatService
from license_manager.models import ActivateRequest, HeartbeatRequest, HeartbeatResponse, LicensePayload
from license_manager.storage import FileStore, Store
from license_manager.validator import Validator


class Callbacks:
    def __init__(
        self,
        on_license_updated: Optional[Callable[[LicensePayload], None]] = None,
        on_heartbeat_error: Optional[Callable[[Exception], None]] = None,
        on_activation_required: Optional[Callable[[str], None]] = None,
        on_heartbeat_ping: Optional[Callable[[], None]] = None
    ):
        self.on_license_updated = on_license_updated
        self.on_heartbeat_error = on_heartbeat_error
        self.on_activation_required = on_activation_required
        self.on_heartbeat_ping = on_heartbeat_ping


class ClientOptions:
    def __init__(
        self,
        hardware_provider: Optional[HardwareProvider] = None,
        store: Optional[Store] = None,
        callbacks: Optional[Callbacks] = None
    ):
        self.hardware_provider = hardware_provider
        self.store = store
        self.callbacks = callbacks or Callbacks()


class Client:
    def __init__(self, cfg: Config, opts: Optional[ClientOptions] = None):
        if not cfg:
            raise ValueError("license: config is required")
            
        cfg.validate()
        pub_key = cfg.resolve_public_key()
        
        self.cfg = cfg
        opts = opts or ClientOptions()
        
        self.store = opts.store or FileStore(cfg.storage_path, cfg.storage_secret)
        self.hardware = opts.hardware_provider or DefaultHardwareProvider(cfg.hardware_fields)
        self.callbacks = opts.callbacks
        
        self.validator = Validator(pub_key)
        self.activate_svc = ActivationService(cfg)
        self.heartbeat_svc = HeartbeatService(cfg)
        self.heartbeat_manager: Optional[HeartbeatManager] = None
        
        try:
            fp, details = self.hardware.fingerprint()
            self.fingerprint = fp
            self.fp_details = details
        except Exception as e:
            raise ValueError(f"license: collect fingerprint: {e}")
            
        self.license_key = ""
        self.current: Optional[LicensePayload] = None
        
        self._lock = threading.RLock()
        
        self._bootstrap()

    def validate(self) -> None:
        """Re-validates the current license."""
        with self._lock:
            lic = self.current
            
        if not lic:
            raise ValueError("license: no loaded license")
            
        if lic.expires_at:
            now = datetime.now(timezone.utc)
            exp = lic.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
                
            if now > exp:
                raise ValueError("license: expired")

    def current_license(self) -> Optional[LicensePayload]:
        """Returns a copy of the payload."""
        with self._lock:
            if not self.current:
                return None
            # Return a shallow copy is usually enough for python dataclass
            # but standard deepcopy would be strictly safer if user modifies dicts inside
            import copy
            return copy.deepcopy(self.current)

    def pause_heartbeat(self):
        """Temporarily halts heartbeat loop."""
        if self.heartbeat_manager:
            self.heartbeat_manager.pause()

    def resume_heartbeat(self):
        """Resumes heartbeat loop."""
        if self.heartbeat_manager:
            self.heartbeat_manager.resume()

    def close(self):
        """Shuts down background threads."""
        if self.heartbeat_manager:
            self.heartbeat_manager.stop()

    def _bootstrap(self):
        self._load_existing()
        
        if self.current:
            if not self.cfg.offline:
                self._start_heartbeat()
            return
            
        if self.cfg.offline:
            raise ValueError("license: offline mode requires preloaded license")
            
        self._perform_activation()
        self._start_heartbeat()

    def _load_existing(self):
        try:
            data = self.store.load()
            if not data:
                return
                
            payload = self._validate_and_store(data)
            with self._lock:
                self.current = payload
                self.license_key = payload.license_key
        except Exception:
            pass

    def _perform_activation(self):
        device_info = dict(self.cfg.device_info or {})
        if self.fp_details:
            device_info["hardware"] = self.fp_details
            
        req = ActivateRequest(
            authorization_code=self.cfg.authorization_code,
            product=self.cfg.product,
            version=self.cfg.version,
            hardware_fingerprint=self.fingerprint,
            device_info=device_info,
            metadata=self.cfg.metadata
        )
        
        try:
            resp = self.activate_svc.activate(req)
        except Exception as e:
            if self.callbacks.on_activation_required:
                try:
                    self.callbacks.on_activation_required(str(e))
                except Exception:
                    pass
            raise
            
        if not resp.license_file:
            raise ValueError("license: activation response missing license file")
            
        payload = self._apply_license_file(resp.license_file)
        
        with self._lock:
            self.license_key = resp.license_key

    def _apply_license_file(self, base64_file: str) -> LicensePayload:
        try:
            raw = base64.b64decode(base64_file)
        except Exception as e:
            raise ValueError(f"license: decode license file: {e}")
            
        payload = self._validate_and_store(raw)
        
        with self._lock:
            self.current = payload
            if self.callbacks.on_license_updated:
                threading.Thread(target=self.callbacks.on_license_updated, args=(payload,), daemon=True).start()
                
        return payload

    def _validate_and_store(self, raw: bytes) -> LicensePayload:
        normalized = self._normalize_license_bytes(raw)
        payload = self.validator.verify(normalized, self.fingerprint)
        
        try:
            self.store.save(normalized)
        except Exception as e:
            raise ValueError(f"license: persist license: {e}")
            
        return payload

    def _start_heartbeat(self):
        with self._lock:
            license_key = self.license_key
            
        if not license_key:
            return
            
        req = HeartbeatRequest(
            license_key=license_key,
            hardware_fingerprint=self.fingerprint
        )
        
        interval = self.cfg.heartbeat_interval_or_default()
        
        def on_update(resp: HeartbeatResponse):
            try:
                if resp.license_file:
                    self._apply_license_file(resp.license_file)
            except Exception:
                pass
                
            if resp.status == "activation_required" and self.callbacks.on_activation_required:
                try:
                    self.callbacks.on_activation_required("heartbeat requested reactivation")
                except Exception:
                    pass
                    
        def on_error(err: Exception):
            if self.callbacks.on_heartbeat_error:
                try:
                    self.callbacks.on_heartbeat_error(err)
                except Exception:
                    pass
                    
        mgr = HeartbeatManager(
            service=self.heartbeat_svc,
            req=req,
            interval_seconds=interval,
            on_license_updated=on_update,
            on_error=on_error,
            on_ping=self.callbacks.on_heartbeat_ping
        )
        mgr.start()
        self.heartbeat_manager = mgr

    def _normalize_license_bytes(self, raw: bytes) -> bytes:
        trimmed = raw.strip()
        if not trimmed:
            raise ValueError("license: empty license file")
            
        if trimmed.startswith(b'{'):
            return trimmed
            
        try:
            decoded = base64.b64decode(trimmed)
            decoded = decoded.strip()
            if not decoded or not decoded.startswith(b'{'):
                raise ValueError("unsupported structure")
            return decoded
        except Exception as e:
            raise ValueError(f"license: decode base64 license: {e}")
