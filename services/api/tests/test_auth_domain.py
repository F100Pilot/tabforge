"""Pure auth logic (US-07): email normalization, tokens, CSRF comparison, magic-link text."""

import hashlib

import pytest

from tabforge_api import auth


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ana@example.com", "ana@example.com"),
        ("  Ana.Silva+tabs@Example.PT ", "ana.silva+tabs@example.pt"),
        ("o'neil@sub.example.co.uk", "o'neil@sub.example.co.uk"),
    ],
)
def test_normalize_email_accepts_and_lowercases(raw: str, expected: str) -> None:
    assert auth.normalize_email(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "ana",
        "ana@",
        "@example.com",
        "ana@example",  # no dot in the domain
        "ana@@example.com",
        "ana @example.com",
        "ana@exa mple.com",
        "ana@example.com\r\nBcc: victim@example.com",  # header injection
        "ana@-example.com",
        "ana@example-.com",
        "ana@example..com",
        "ana@例え.jp",  # IDN not accepted (conservative ASCII check)
        "a" * 65 + "@example.com",  # local part > 64
        "a@" + ".".join(["b" * 60] * 4 + ["c" * 9]),  # 255 > 254 overall
        "a@" + "b" * 64 + ".com",  # domain label > 63
    ],
)
def test_normalize_email_rejects_invalid(raw: str) -> None:
    assert auth.normalize_email(raw) is None


def test_email_at_254_chars_is_accepted() -> None:
    domain = ".".join(["b" * 60] * 4 + ["c" * 8])
    email = f"a@{domain}"
    assert len(email) == 254
    assert auth.normalize_email(email) == email


def test_new_token_is_urlsafe_and_unique() -> None:
    tokens = {auth.new_token() for _ in range(100)}
    assert len(tokens) == 100
    for token in tokens:
        assert len(token) >= 43  # 32 random bytes, base64url
        assert set(token) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_hash_token_is_sha256_hex() -> None:
    assert auth.hash_token("abc") == hashlib.sha256(b"abc").hexdigest()
    assert auth.hash_token("abc") != auth.hash_token("abd")


@pytest.mark.parametrize(
    ("given", "ok"),
    [("s3cret", True), ("s3cre", False), ("S3CRET", False), ("", False), (None, False)],
)
def test_csrf_matches(given: str | None, ok: bool) -> None:
    assert auth.csrf_matches("s3cret", given) is ok


@pytest.mark.parametrize(
    ("method", "unsafe"),
    [
        ("GET", False),
        ("HEAD", False),
        ("OPTIONS", False),
        ("POST", True),
        ("put", True),
        ("PATCH", True),
        ("DELETE", True),
    ],
)
def test_unsafe_methods(method: str, unsafe: bool) -> None:
    assert auth.is_unsafe_method(method) is unsafe


@pytest.mark.parametrize("base", ["http://localhost:3000", "http://localhost:3000/"])
def test_magic_link_url_puts_token_in_fragment(base: str) -> None:
    assert auth.magic_link_url(base, "tok") == "http://localhost:3000/login/verify#token=tok"


def test_magic_link_url_keeps_base_path() -> None:
    assert auth.magic_link_url("https://x.pt/app/", "t") == "https://x.pt/app/login/verify#token=t"


def test_magic_link_message_is_portuguese_and_contains_link() -> None:
    subject, body = auth.magic_link_message("https://x.pt/login/verify#token=t", ttl_s=900)
    assert "TabForge" in subject
    assert "https://x.pt/login/verify#token=t" in body
    assert "15 minutos" in body
    assert "ignorar" in body  # "if it wasn't you, you can ignore this email"
