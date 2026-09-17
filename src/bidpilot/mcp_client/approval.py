import hashlib
import hmac
import json
import time


def sign_approval(payload, secret, expires=None):
    expires = expires or int(time.time()) + 300
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    signature = hmac.new(secret.encode(), f"{expires}:{data}".encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{signature}"


def verify_approval(payload, token, secret):
    try:
        expiry = int(token.split(".")[0])
        return int(time.time()) <= expiry <= int(time.time()) + 360 and hmac.compare_digest(
            token, sign_approval(payload, secret, expiry)
        )
    except (ValueError, IndexError):
        return False
