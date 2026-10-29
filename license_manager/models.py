import base64
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class LicensePayload:
    license_key: str
    authorization_code: str
    hardware_fingerprint: str
    status: str
    start_date: datetime
    end_date: datetime
    expires_at: datetime

    product: Optional[str] = None
    version: Optional[str] = None
    authorization_code_id: Optional[str] = None
    deployment_type: Optional[str] = None
    max_activations: Optional[int] = None

    custom_parameters: Dict[str, Any] = field(default_factory=dict)
    feature_config: Dict[str, Any] = field(default_factory=dict)
    usage_limits: Dict[str, Any] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)

    activated_at: Optional[datetime] = None
    generated_at: Optional[datetime] = None
    config_updated_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: dict) -> "LicensePayload":
        def parse_time(val):
            if not val:
                return None
            # Go's time.RFC3339 / ISO 8601 parsing approximation
            try:
                # Handle Z timezone
                if isinstance(val, str) and val.endswith("Z"):
                    val = val[:-1] + "+00:00"
                return datetime.fromisoformat(val)
            except Exception:
                return None

        # expires_at is not explicitly in JSON sometimes, handled differently in Go?
        # In Go, ExpiresAt is populated by the validator based on EndDate or similar logic,
        # or from a different field. We'll set it to end_date as default parser.

        args = {
            "license_key": data.get("license_key", ""),
            "authorization_code": data.get("authorization_code", ""),
            "hardware_fingerprint": data.get("hardware_fingerprint", ""),
            "status": data.get("status", ""),
            "start_date": parse_time(data.get("start_date")),
            "end_date": parse_time(data.get("end_date")),
            "product": data.get("product"),
            "version": data.get("version"),
            "authorization_code_id": data.get("authorization_code_id"),
            "deployment_type": data.get("deployment_type"),
            "max_activations": data.get("max_activations"),
            "custom_parameters": data.get("custom_parameters", {}),
            "feature_config": data.get("feature_config", {}),
            "usage_limits": data.get("usage_limits", {}),
            "extras": data.get("extras", {}),
            "activated_at": parse_time(data.get("activated_at")),
            "generated_at": parse_time(data.get("generated_at")),
            "config_updated_at": parse_time(data.get("config_updated_at")),
        }

        # In Go ExpiresAt has json:"-" meaning it's internal.
        args["expires_at"] = args["end_date"]

        return cls(**args)


@dataclass
class LicenseEnvelope:
    algorithm: str
    data: str
    signature: str

    @classmethod
    def from_dict(cls, data: dict) -> "LicenseEnvelope":
        return cls(
            algorithm=data.get("algorithm", ""),
            data=data.get("data", ""),
            signature=data.get("signature", ""),
        )


@dataclass
class ActivateRequest:
    authorization_code: str
    product: str
    version: str
    hardware_fingerprint: str
    software_version: Optional[str] = None
    device_info: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "authorization_code": self.authorization_code,
            "product": self.product,
            "version": self.version,
            "hardware_fingerprint": self.hardware_fingerprint,
            "software_version": self.software_version,
            "device_info": self.device_info,
            "metadata": self.metadata,
        }


@dataclass
class ActivateResponse:
    license_key: str
    license_file: str
    heartbeat_interval: int
    payload: Optional[LicensePayload] = None
    public_key: Optional[str] = None  # 服务端返回的最新公钥

    @classmethod
    def from_dict(cls, data: dict) -> "ActivateResponse":
        payload_data = data.get("payload")
        payload = LicensePayload.from_dict(payload_data) if payload_data else None
        return cls(
            license_key=data.get("license_key", ""),
            license_file=data.get("license_file", ""),
            heartbeat_interval=data.get("heartbeat_interval", 0),
            payload=payload,
            public_key=data.get("public_key"),
        )


@dataclass
class HeartbeatRequest:
    license_key: str
    hardware_fingerprint: str
    software_version: Optional[str] = None
    usage_data: Dict[str, Any] = field(default_factory=dict)
    config_updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        d = {
            "license_key": self.license_key,
            "hardware_fingerprint": self.hardware_fingerprint,
        }
        if self.software_version is not None:
            d["software_version"] = self.software_version
        if self.usage_data:
            d["usage_data"] = self.usage_data
        if self.config_updated_at:
            d["config_updated_at"] = self.config_updated_at.isoformat()
        return d


@dataclass
class HeartbeatResponse:
    status: str
    license_file: Optional[str] = None
    heartbeat_interval: Optional[int] = None
    config_updated: Optional[bool] = None
    payload: Optional[LicensePayload] = None

    @classmethod
    def from_dict(cls, data: dict) -> "HeartbeatResponse":
        payload_data = data.get("payload")
        payload = LicensePayload.from_dict(payload_data) if payload_data else None
        return cls(
            status=data.get("status", ""),
            license_file=data.get("license_file"),
            heartbeat_interval=data.get("heartbeat_interval"),
            config_updated=data.get("config_updated"),
            payload=payload,
        )


@dataclass
class APIError:
    code: str
    message: str
    timestamp: str

    @classmethod
    def from_dict(cls, data: dict) -> "APIError":
        return cls(
            code=data.get("code", ""),
            message=data.get("message", ""),
            timestamp=data.get("timestamp", ""),
        )
