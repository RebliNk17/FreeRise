import os

import pytest
from cryptography.exceptions import InvalidTag

from freerise.crypto import decrypt_json, decrypt_str, encrypt_json, encrypt_str, mask


def test_roundtrip():
    d = {"username": "u", "password": "p"}
    assert decrypt_json(encrypt_json(d)) == d
    assert decrypt_str(encrypt_str("hello")) == "hello"


def test_ciphertext_differs_each_time():
    assert encrypt_json({"a": 1}) != encrypt_json({"a": 1})


def test_tampered_blob_rejected():
    b = bytearray(encrypt_json({"a": 1}))
    b[-1] ^= 1
    with pytest.raises(InvalidTag):
        decrypt_json(bytes(b))


def test_wrong_key_rejected():
    blob = encrypt_json({"a": 1})
    with pytest.raises(InvalidTag):
        decrypt_json(blob, key=os.urandom(32))


def test_bad_key_length():
    with pytest.raises(ValueError, match="32 bytes"):
        encrypt_json({"a": 1}, key=b"short")


def test_mask_hides_password():
    assert mask({"password": "x", "card6Digits": "123456"}) == {
        "password": "••••",
        "card6Digits": "••56",
    }
