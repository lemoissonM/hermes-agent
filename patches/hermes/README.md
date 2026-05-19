# Hermes vendor patches for Symposa

Pin the upstream commit in `VENDOR_SHA` when merging from NousResearch/hermes-agent.

## Applied in-tree (this fork)

1. **Unified memory key** — `gateway/run.py`
   - `_resolve_gateway_session_key()` reads `symposa.runtime.context.get_memory_key()`
   - `AIAgent(gateway_session_key=...)` uses cross-channel Symposa key when set

2. **Plugin dispatch replies** — `gateway/run.py`
   - `pre_gateway_dispatch` skip may include `send_reply` text (WhatsApp `/conv`, link prompts)

3. **Skill overrides** — `tools/skills_tool.py`
   - `skill_view()` checks Postgres overrides when Symposa context is active

4. **Per-request toolsets** — `gateway/platforms/api_server.py`
   - Honors `X-Hermes-Enabled-Toolsets` (comma-separated) on `/v1/chat/completions`
   - Symposa chat proxy sends company agent toolsets (default `symposa-workspace`)

5. **Per-request HERMES_HOME** — `hermes_constants.py` + `gateway/platforms/api_server.py` + `tools/environments/local.py`
   - `set_hermes_home_override()` / `reset_hermes_home_override()` via `ContextVar`
   - api_server honors `X-Symposa-Hermes-Home` (absolute POSIX path) on `/v1/chat/completions`
   - Symposa chat proxy sends WSL-visible per-user `.hermes` dir after credential materialization
   - `_make_run_env()` injects `HERMES_HOME` from `get_hermes_home()` so skill subprocesses see per-user tokens
   - `google-workspace/scripts/google_api.py` resolves token paths at call time (not import time)

## Upgrade runbook

```bash
git fetch upstream
git diff upstream/main -- gateway/run.py tools/skills_tool.py
# Re-apply changes if conflicts
export SYMPOSA_DATABASE_URL=postgresql+psycopg://...
alembic -c symposa/db/alembic.ini upgrade head
```
