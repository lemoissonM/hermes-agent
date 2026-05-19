"""auth.json sanitization for Symposa per-user homes."""

import json

from symposa.services.inference_config import sanitize_auth_json


def test_sanitize_auth_json_removes_credential_pool(tmp_path):
    home = tmp_path / ".hermes"
    home.mkdir()
    path = home / "auth.json"
    path.write_text(
        json.dumps({"credential_pool": {"kimi": []}, "openrouter": {"api_key": "x"}}),
        encoding="utf-8",
    )
    assert sanitize_auth_json(home) is True
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "credential_pool" not in data
    assert data["openrouter"]["api_key"] == "x"


def test_sanitize_auth_json_noop_when_missing(tmp_path):
    home = tmp_path / ".hermes"
    home.mkdir()
    assert sanitize_auth_json(home) is False
