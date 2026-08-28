"""Ed25519 keypair management + evidence signing/verification.

A local keypair is generated on first run and stored under backend/data/keys.
This provides real, independently-verifiable tamper-evidence for evidence
clips (a re-hash + signature check), which is explicitly NOT the same as
a "court-certified" claim -- none is made anywhere in this system.
"""
import base64
import hashlib
import threading

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.config import ED25519_PRIVATE_KEY_PATH, ED25519_PUBLIC_KEY_PATH

_private_key: Ed25519PrivateKey | None = None
_public_key: Ed25519PublicKey | None = None
_keys_lock = threading.Lock()


def _ensure_keys():
    global _private_key, _public_key
    if _private_key is not None:
        return
    # Double-checked locking: two near-simultaneous first requests (evidence
    # capture runs on FastAPI's threadpool) could otherwise both see
    # _private_key is None, both generate a *different* keypair, and race to
    # write the key files -- whichever wrote last wins on disk, silently
    # leaving the other thread's already-issued signature unverifiable
    # forever against the persisted key.
    with _keys_lock:
        if _private_key is not None:
            return
        if ED25519_PRIVATE_KEY_PATH.exists():
            _private_key = serialization.load_pem_private_key(ED25519_PRIVATE_KEY_PATH.read_bytes(), password=None)
        else:
            _private_key = Ed25519PrivateKey.generate()
            ED25519_PRIVATE_KEY_PATH.write_bytes(
                _private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
            ED25519_PUBLIC_KEY_PATH.write_bytes(
                _private_key.public_key().public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )
        _public_key = _private_key.public_key()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sign_digest(sha256_hex: str) -> str:
    _ensure_keys()
    signature = _private_key.sign(sha256_hex.encode("utf-8"))
    return base64.b64encode(signature).decode("ascii")


def verify_digest(sha256_hex: str, signature_b64: str) -> bool:
    _ensure_keys()
    try:
        _public_key.verify(base64.b64decode(signature_b64), sha256_hex.encode("utf-8"))
        return True
    except Exception:
        return False


def public_key_pem() -> str:
    _ensure_keys()
    return _public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
