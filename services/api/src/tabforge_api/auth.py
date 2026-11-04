"""US-07 auth domain logic (ADR-0006): magic-link tokens, opaque sessions, CSRF.

Pure functions only; the HTTP routes live in routes/auth.py and the request dependency in deps.py.
Secrets (login tokens, session cookies) are stored only as SHA-256 hashes.
"""

import hashlib
import hmac
import re
import secrets

SESSION_COOKIE = "tabforge_session"
CSRF_HEADER = "X-CSRF-Token"
MAX_EMAIL_LENGTH = 254  # RFC 5321 path limit
MAX_TOKEN_LENGTH = 128  # issued tokens are 43 chars; anything longer is not ours

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Conservative ASCII subset of RFC 5322 (no quoted local parts, no IDN, no IP literals).
_LOCAL = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*")
_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


def normalize_email(raw: str) -> str | None:
    """Trimmed, lowercased email if it passes a conservative syntax check, else None."""
    email = raw.strip().lower()
    if len(email) > MAX_EMAIL_LENGTH or email.count("@") != 1:
        return None
    local, domain = email.split("@")
    if len(local) > 64 or not _LOCAL.fullmatch(local):
        return None
    labels = domain.split(".")
    if len(labels) < 2 or not all(_LABEL.fullmatch(label) for label in labels):
        return None
    return email


def new_token() -> str:
    """256 bits of randomness, URL-safe (login tokens, session cookies, CSRF tokens)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_matches(expected: str, given: str | None) -> bool:
    """Synchronizer-token check in constant time."""
    if not given:
        return False
    return hmac.compare_digest(expected.encode(), given.encode())


def is_unsafe_method(method: str) -> bool:
    return method.upper() not in _SAFE_METHODS


def magic_link_url(web_base_url: str, token: str) -> str:
    """Link to the web app; the token goes in the fragment so it never reaches server logs."""
    return f"{web_base_url.rstrip('/')}/login/verify#token={token}"


def magic_link_message(link: str, ttl_s: int) -> tuple[str, str]:
    """Subject and plain-text body (European Portuguese)."""
    minutes = max(1, ttl_s // 60)
    subject = "O seu link de acesso ao TabForge"
    body = (
        "Olá,\n\n"
        "Recebemos um pedido para entrar no TabForge com este email.\n"
        "Abra este link para entrar:\n\n"
        f"{link}\n\n"
        f"O link é válido durante {minutes} minutos e só pode ser usado uma vez.\n"
        "Se não fez este pedido, pode ignorar este email.\n\n"
        "— TabForge\n"
    )
    return subject, body
