import os
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class Config:
    server: str = ""
    base_path: str = ""
    product: str = ""
    version: str = ""
    authorization_code: str = ""
    authorization_code_path: str = ""
    license_file_path: str = ""
    
    public_key_pem: bytes = b""
    public_key_path: str = ""
    
    offline: bool = False
    
    heartbeat_interval_seconds: int = 0
    http_timeout_seconds: int = 0
    
    log_level: str = "info"
    
    storage_path: str = ""
    storage_secret: bytes = b""
    
    hardware_fields: List[str] = field(default_factory=list)
    
    device_info: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    http_headers: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.product:
            raise ValueError("config: product is required")
        if not self.version:
            raise ValueError("config: version is required")
        if not self.offline and not self.server:
            raise ValueError("config: server is required for online mode")
        if not self.offline and not self.authorization_code and not self.authorization_code_path and not self.license_file_path:
            raise ValueError("config: authorization code, authorization code path, or license file path is required")
            
        if not self.license_file_path:
            self.license_file_path = os.path.join("license_code", "license.lic")
            
        if not self.storage_path:
            self.storage_path = self.license_file_path
            
        self.resolve_public_key()
        
        if not self.offline:
            self.resolve_authorization_code()

    def resolve_public_key(self) -> bytes:
        if self.public_key_pem:
            return self.public_key_pem
        if not self.public_key_path:
            raise ValueError("config: public key pem or path must be provided")
            
        try:
            with open(self.public_key_path, 'rb') as f:
                data = f.read()
            self.public_key_pem = data
            return data
        except Exception as e:
            raise ValueError(f"config: read public key: {e}")

    def resolve_authorization_code(self) -> str:
        if self.authorization_code:
            self.authorization_code = self.authorization_code.strip()
            return self.authorization_code
            
        if not self.authorization_code_path:
            raise ValueError("config: authorization code or path must be provided")
            
        try:
            with open(self.authorization_code_path, 'r', encoding='utf-8') as f:
                code = f.read().strip()
            if not code:
                raise ValueError("config: authorization code file is empty")
            self.authorization_code = code
            return code
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"config: read authorization code: {e}")

    def heartbeat_interval_or_default(self) -> int:
        if self.heartbeat_interval_seconds > 0:
            return self.heartbeat_interval_seconds
        return 300  # Default 5 minutes

    def http_timeout_or_default(self) -> int:
        if self.http_timeout_seconds > 0:
            return self.http_timeout_seconds
        return 15  # Default 15 seconds
