import json
from typing import Dict, Optional

import requests
from requests.exceptions import RequestException

from license_manager.config import Config
from license_manager.models import ActivateRequest, ActivateResponse


class ActivationService:
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

    def activate(self, req: ActivateRequest) -> ActivateResponse:
        url = f"{self.base_url}/api/v1/activate"
        payload = req.to_dict()

        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
        except RequestException as e:
            raise ValueError(f"activation: network error: {e}")

        try:
            resp_data = resp.json()
        except ValueError:
            raise ValueError(f"activation: decode response failed, status {resp.status_code}")

        if resp.status_code >= 300:
            if isinstance(resp_data, dict) and "message" in resp_data:
                msg = resp_data.get("message", "")
                code = resp_data.get("code", "")
                raise ValueError(f"activation: {msg} ({code})")
            raise ValueError(f"activation: status {resp.status_code}")

        code = resp_data.get("code", "")
        message = resp_data.get("message", "")

        if code and str(code) != "000000":
            raise ValueError(f"activation: {message} ({code})")

        data = resp_data.get("data")
        if not data:
            raise ValueError("activation: response missing data")

        return ActivateResponse.from_dict(data)
