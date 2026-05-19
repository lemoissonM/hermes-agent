# Symposa upgrade runbook

1. Pin Hermes upstream SHA in `patches/hermes/VENDOR_SHA` (create file on release).
2. Reconcile `gateway/run.py` and `tools/skills_tool.py` Symposa hooks after merging upstream.
3. Run database migrations:
   ```bash
   alembic -c symposa/db/alembic.ini upgrade head
   ```
4. Restart `symposa-api` and gateway with `SYMPOSA_COMPANY_ID` set.
5. Verify plugin loads: `HERMES_PLUGINS_DEBUG=1 hermes gateway` — look for "Symposa plugin registered".

## Environment

| Variable | Purpose |
|----------|---------|
| `SYMPOSA_DATABASE_URL` | Postgres connection |
| `SYMPOSA_JWT_SECRET` | API auth |
| `SYMPOSA_COMPANY_ID` | Default company for gateway WhatsApp routing |
| `SYMPOSA_RUNTIME_ROOT` | Per-user materialized HERMES_HOME parent |
| `SYMPOSA_HERMES_API_URL` | Hermes api_server base URL |
| `SYMPOSA_CREDENTIAL_ENCRYPTION_KEY` | Fernet key for OAuth blobs |

Generate Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
