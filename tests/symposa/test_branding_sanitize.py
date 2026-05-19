"""Symposa user-facing text sanitization."""

from plugins.symposa import _sanitize_user_facing_text


def test_sanitize_replaces_infrastructure_leaks():
    text = "Configure Hermes and google_token.json; try himalaya instead."
    out = _sanitize_user_facing_text(text)
    assert "Hermes" not in out
    assert "google_token.json" not in out
    assert "Symposa" in out


def test_sanitize_replaces_base_model_identity():
    text = "Hello! I am a large language model, trained by Google. I can help."
    out = _sanitize_user_facing_text(text)
    assert "large language model" not in out
    assert "trained by Google" not in out
    assert "I'm Symposa" in out
