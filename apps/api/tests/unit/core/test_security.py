import uuid

from gpuwatch.core.security import (
    decode_session,
    generate_api_key,
    hash_key_secret,
    hash_password,
    issue_session,
    parse_api_key,
    password_problems,
    verify_password,
)

PEPPER = "test-only-pepper"
SECRET = "test-only-session-secret-with-32-plus-bytes"


def test_api_key_round_trip() -> None:
    key = generate_api_key(PEPPER)
    parsed = parse_api_key(key.plaintext)
    assert parsed is not None
    prefix, secret = parsed
    assert prefix == key.prefix
    assert hash_key_secret(secret, PEPPER) == key.secret_hash
    assert key.plaintext.startswith(f"gwk_{prefix}_")


def test_api_key_hash_depends_on_pepper() -> None:
    key = generate_api_key(PEPPER)
    _, secret = parse_api_key(key.plaintext)  # type: ignore[misc]
    assert hash_key_secret(secret, "another-pepper") != key.secret_hash


def test_parse_rejects_malformed_keys() -> None:
    for raw in ("", "sk-abc", "gwk_short_x", "gwk_abcdefabcdef_", "xyz_abcdefabcdef_secret"):
        assert parse_api_key(raw) is None


def test_two_keys_never_collide() -> None:
    a, b = generate_api_key(PEPPER), generate_api_key(PEPPER)
    assert a.prefix != b.prefix and a.plaintext != b.plaintext


def test_password_hash_and_verify() -> None:
    h = hash_password("Correct-horse-1")
    assert verify_password("Correct-horse-1", h)
    assert not verify_password("wrong", h)
    assert not verify_password("anything", None)
    assert not verify_password("anything", "not-a-hash")


def test_password_policy() -> None:
    assert password_problems("Str0ngPassword") == []
    assert "at least 10 characters" in password_problems("Ab1")
    assert "upper and lower case letters" in password_problems("lowercase123")
    assert "a digit" in password_problems("NoDigitsHere")


def test_session_round_trip_and_tamper() -> None:
    uid = uuid.uuid4()
    token = issue_session(uid, "admin", 3, SECRET, 1)
    claims = decode_session(token, SECRET)
    assert claims is not None
    assert (claims.user_id, claims.role, claims.session_version) == (uid, "admin", 3)
    assert decode_session(token, "test-only-other-secret-with-32-plus-bytes") is None
    assert decode_session(token[:-2] + "xx", SECRET) is None
    assert decode_session("garbage", SECRET) is None


def test_expired_session_is_rejected() -> None:
    token = issue_session(uuid.uuid4(), "viewer", 0, SECRET, -1)
    assert decode_session(token, SECRET) is None


def test_token_kinds_do_not_cross() -> None:
    from gpuwatch.core.security import ENROLMENT_PREFIX, HOST_TOKEN_PREFIX

    host = generate_api_key("pepper", HOST_TOKEN_PREFIX)
    assert host.plaintext.startswith("gwh_")
    assert parse_api_key(host.plaintext) is None  # not an API key
    assert parse_api_key(host.plaintext, HOST_TOKEN_PREFIX) is not None
    assert parse_api_key(host.plaintext, ENROLMENT_PREFIX) is None
