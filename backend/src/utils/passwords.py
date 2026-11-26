import hashlib
import hmac
import secrets


def derive(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000).hex()


def hash_password(password):
    salt = secrets.token_bytes(16)
    return f"{salt.hex()}:{derive(password, salt)}"


def verify_password(password, stored):
    salt, digest = stored.split(":")
    return hmac.compare_digest(derive(password, bytes.fromhex(salt)), digest)
