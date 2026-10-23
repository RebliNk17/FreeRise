import base64
import json
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from freerise.config import get_settings


@lru_cache
def _settings_key() -> bytes:
    return base64.b64decode(get_settings().credentials_key)


def _aes(key: bytes | None) -> AESGCM:
    key = _settings_key() if key is None else key
    if len(key) != 32:
        raise ValueError("CREDENTIALS_KEY must be 32 bytes base64")
    return AESGCM(key)


def encrypt_str(s: str, *, key: bytes | None = None) -> bytes:
    nonce = os.urandom(12)
    return nonce + _aes(key).encrypt(nonce, s.encode(), None)


def decrypt_str(b: bytes, *, key: bytes | None = None) -> str:
    return _aes(key).decrypt(b[:12], b[12:], None).decode()


def encrypt_json(data: dict, *, key: bytes | None = None) -> bytes:
    return encrypt_str(json.dumps(data), key=key)


def decrypt_json(blob: bytes, *, key: bytes | None = None) -> dict:
    return json.loads(decrypt_str(blob, key=key))


def mask(data: dict) -> dict:
    out = {}
    for k, v in data.items():
        if not v:
            out[k] = v
        elif k == "card6Digits":
            out[k] = "••" + str(v)[-2:]
        else:
            out[k] = "••••"
    return out
