import base64
import json
from datetime import datetime, timezone
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from license_manager.models import LicenseEnvelope, LicensePayload


class Validator:
    def __init__(self, pem_bytes: bytes = b""):
        self.pub = None
        if pem_bytes:
            self._set_pub_key(pem_bytes)

    def _set_pub_key(self, pem_bytes: bytes) -> None:
        if not pem_bytes:
            raise ValueError("validator: missing public key")

        try:
            public_key = load_pem_public_key(pem_bytes)
            if not isinstance(public_key, rsa.RSAPublicKey):
                raise ValueError("validator: public key is not RSA")
            self.pub = public_key
        except ValueError as e:
            if "not RSA" in str(e):
                raise
            raise ValueError(f"validator: parse public key: {e}")

    def verify(self, envelope_bytes: bytes, fingerprint: str) -> LicensePayload:
        if not self.pub:
            raise ValueError("validator: public key not set, activation response may be pending")
        try:
            env_dict = json.loads(envelope_bytes)
            env = LicenseEnvelope.from_dict(env_dict)
        except Exception as e:
            raise ValueError(f"validator: decode license: {e}")

        payload_bytes = env.data.encode("utf-8") if isinstance(env.data, str) else env.data

        try:
            sig = base64.b64decode(env.signature)
        except Exception as e:
            raise ValueError(f"validator: decode signature: {e}")

        self._verify_signature(env.algorithm.upper(), payload_bytes, sig)

        try:
            payload_dict = json.loads(payload_bytes)
            payload = LicensePayload.from_dict(payload_dict)
            payload.extras = payload_dict  # Include everything in extras
        except Exception as e:
            raise ValueError(f"validator: decode payload: {e}")

        if payload.end_date:
            payload.expires_at = payload.end_date

        if (
            fingerprint
            and payload.hardware_fingerprint
            and payload.hardware_fingerprint != fingerprint
        ):
            raise ValueError(
                f"validator: hardware fingerprint mismatch: "
                f"license={payload.hardware_fingerprint} vs local={fingerprint}"
            )

        if payload.expires_at:
            now = datetime.now(timezone.utc)
            # Ensure expires_at is timezone-aware for comparison
            exp = payload.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now > exp:
                raise ValueError("validator: license expired")

        return payload

    def _verify_signature(self, algorithm: str, data: bytes, sig: bytes) -> None:
        try:
            if algorithm in ("", "RSA-SHA256", "RSA-PKCS1V15-SHA256"):
                self.pub.verify(sig, data, padding.PKCS1v15(), hashes.SHA256())
            elif algorithm == "RSA-PSS-SHA256":
                # Go 服务端以 rsa.PSSSaltLengthEqualsHash 签名（盐长=摘要长度），
                # 而部分客户端以 MAX_LENGTH 签发。验签时盐长必须精确匹配，
                # 因此依次尝试 EqualsHash 与 MAX_LENGTH 两种盐长。
                salt_lengths = (
                    hashes.SHA256().digest_size,  # PSSSaltLengthEqualsHash
                    padding.PSS.MAX_LENGTH,
                )
                last_err: Optional[InvalidSignature] = None
                for salt_length in salt_lengths:
                    try:
                        self.pub.verify(
                            sig,
                            data,
                            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=salt_length),
                            hashes.SHA256(),
                        )
                        return
                    except InvalidSignature as e:
                        last_err = e
                raise last_err if last_err else InvalidSignature()
            else:
                self.pub.verify(sig, data, padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature as e:
            raise ValueError(f"validator: signature mismatch: {e}")
        except Exception as e:
            raise ValueError(f"validator: verify error: {e}")
