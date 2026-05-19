"""JWT round-trip tests."""

from uuid import uuid4

from symposa.auth.jwt import create_access_token, decode_token


def test_access_token_roundtrip():
    uid, cid = uuid4(), uuid4()
    token = create_access_token(uid, cid, "member", "u@test.com")
    payload = decode_token(token)
    assert payload["sub"] == str(uid)
    assert payload["company_id"] == str(cid)
    assert payload["type"] == "access"
