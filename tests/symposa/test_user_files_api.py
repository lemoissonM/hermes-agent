"""Per-user file registry, serving, and signed links."""

from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from symposa.auth.jwt import create_access_token
from symposa.api.app import create_app
from symposa.services.files import (
    SOURCE_WORKSPACE,
    mint_share_token,
    public_share_url,
    register_workspace_file,
    resolve_share_token,
    resolve_workspace_path,
    _verify_token,
)
from symposa.services.runtime_paths import user_runtime_root


@pytest.fixture
def api_client(symposa_db, monkeypatch, tmp_path):
    session, company, user_a, user_b = symposa_db
    monkeypatch.setenv("SYMPOSA_LINK_BASE_URL", "http://localhost:3000")
    monkeypatch.setenv("SYMPOSA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    from symposa.config import get_settings

    get_settings.cache_clear()
    app = create_app()

    from contextlib import contextmanager

    @contextmanager
    def _session_scope():
        yield session

    monkeypatch.setattr("symposa.api.app.session_scope", _session_scope)

    client = TestClient(app)
    token_a = create_access_token(user_a.id, company.id, user_a.role, user_a.email)
    token_b = create_access_token(user_b.id, company.id, user_b.role, user_b.email)
    return client, session, company, user_a, user_b, token_a, token_b


def test_register_workspace_file_and_list(api_client):
    client, session, company, user_a, _user_b, token_a, _token_b = api_client
    root = user_runtime_root(user_a.id)
    out_dir = root / "user" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "report.html"
    report.write_text("<html><body>Hi</body></html>", encoding="utf-8")

    row = register_workspace_file(session, company.id, user_a.id, report)
    assert row.source == SOURCE_WORKSPACE
    session.commit()

    resp = client.get("/user/files", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.status_code == 200
    files = resp.json()["files"]
    assert any(f["name"] == "report.html" for f in files)
    assert files[0]["view_url"].endswith("/content")


def test_content_requires_owner(api_client):
    client, session, company, user_a, user_b, token_a, token_b = api_client
    root = user_runtime_root(user_a.id)
    path = root / "user" / "outputs" / "secret.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("private", encoding="utf-8")
    row = register_workspace_file(session, company.id, user_a.id, path)
    session.commit()

    ok = client.get(
        f"/user/files/{row.id}/content",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert ok.status_code == 200
    assert ok.content == b"private"

    denied = client.get(
        f"/user/files/{row.id}/content",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert denied.status_code == 404


def test_signed_public_link(api_client):
    client, session, company, user_a, _user_b, token_a, _token_b = api_client
    root = user_runtime_root(user_a.id)
    path = root / "user" / "outputs" / "shared.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<html><body>Public</body></html>", encoding="utf-8")
    row = register_workspace_file(session, company.id, user_a.id, path)
    session.commit()

    token, _ttl = mint_share_token(row)
    pub = client.get(f"/public/files/{token}")
    assert pub.status_code == 200
    assert b"Public" in pub.content
    assert "text/html" in pub.headers.get("content-type", "")


def test_signed_token_expired():
    from symposa.services.files import _sign_payload

    payload = {"file_id": str(uuid4()), "user_id": str(uuid4()), "company_id": str(uuid4()), "exp": 1}
    token = _sign_payload(payload)
    time.sleep(1.1)
    assert _verify_token(token) is None


def test_path_traversal_blocked(symposa_db, tmp_path, monkeypatch):
    _session, _company, user_a, _user_b = symposa_db
    monkeypatch.setenv("SYMPOSA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    from symposa.config import get_settings

    get_settings.cache_clear()
    outside = tmp_path / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(PermissionError):
        resolve_workspace_path(user_a.id, f"../../../outside.txt")


def test_transform_tool_result_injects_urls(symposa_db, tmp_path, monkeypatch):
    session, company, user_a, _user_b = symposa_db
    monkeypatch.setenv("SYMPOSA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SYMPOSA_LINK_BASE_URL", "http://localhost:3000")
    from symposa.config import get_settings
    from symposa.runtime.context import SymposaContext, set_context, clear_context

    get_settings.cache_clear()
    root = user_runtime_root(user_a.id)
    path = root / "user" / "outputs" / "out.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Hello", encoding="utf-8")

    ctx = SymposaContext(
        company_id=company.id,
        user_id=user_a.id,
        conversation_id=uuid4(),
        memory_key="symposa:test",
        runtime_root=str(root),
        channel="web",
    )
    set_context(ctx)

    def _session_scope():
        from contextlib import contextmanager

        @contextmanager
        def cm():
            yield session

        return cm()

    monkeypatch.setattr("symposa.db.session.session_scope", _session_scope)

    from plugins.symposa import _transform_tool_result

    raw = json.dumps({"success": True, "path": str(path)})
    out = _transform_tool_result(
        tool_name="write_file",
        args={"path": str(path)},
        result=raw,
    )
    clear_context()
    assert out is not None
    data = json.loads(out)
    assert data.get("view_url")
    assert data.get("share_url")
    assert data.get("file_id")
