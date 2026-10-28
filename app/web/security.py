"""Security helpers kept separate for future authentication integration."""
import hmac
from hashlib import sha256


def sign_payload(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), sha256).hexdigest()


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
