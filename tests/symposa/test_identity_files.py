"""Identity markdown loading from runtime dirs."""

from uuid import uuid4

from symposa.config import get_settings
from symposa.services.identity_files import load_identity_files_block
from symposa.services.runtime_paths import user_runtime_root


def test_load_identity_files_block(monkeypatch, tmp_path):
    user_id = uuid4()
    monkeypatch.setenv("SYMPOSA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.delenv("SYMPOSA_RUNTIME_WSL_ROOT", raising=False)
    get_settings.cache_clear()

    root = user_runtime_root(user_id)
    (root / "user").mkdir(parents=True)
    (root / "user" / "profile.md").write_text("I prefer concise replies.", encoding="utf-8")

    block = load_identity_files_block(user_id)
    assert "Identity files" in block
    assert "concise replies" in block
