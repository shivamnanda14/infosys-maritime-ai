# FreightQuote AI — Deployment & Verification

## Colab notebook

1. Open `FreightQuote_AI_Milestone2_Final_Deployment.ipynb` in **Google Colab** and select a CPU runtime.
2. Configure Colab **Secrets**: `JWT_SECRET` (stable random string at least 32 characters), `ADMIN_PASSWORD` (unique 12–72-byte strong password), `ADMIN_EMAIL`; also `EMAIL_ADDRESS` + `EMAIL_PASSWORD` for Gmail SMTP OTP verification. Make sure notebook access to those secrets is enabled.
3. Run all cells in order. The notebook uses Colab’s existing Python (no virtualenv / ensurepip). The last cell restores missing app assets, validates the server, checks admin login and nine authenticated pages, and provides a Colab proxy link. For an optional public tunnel configure `NGROK_AUTHTOKEN`.
4. Select **Admin** in the sign-in role dropdown. For new users, choose **Customer** (public signup creates Customer accounts). Internal roles are assigned by an administrator, not by signup or choosing a role in sign-in.
5. Verify email OTP with a real configured email address. Without SMTP, email verification cannot be completed; an admin can still sign in and manage accounts.
6. Keep in mind the Colab runtime is temporary; `/content/freightquote_data` must be separately persisted if you need durable data.

## Docker (single instance, reverse-proxy HTTPS required for public use)

1. `cp .env.example .env`, then edit `.env` with real secrets; never commit it.
2. `docker compose up --build -d`.
3. Open `http://localhost:8000` locally. For public deployment, use HTTPS through a reverse proxy and require authentication. Never expose a test/demo app with real customer data as-is.
4. The container persists SQLite data in a named volume. Keep only **one** uvicorn worker and **one app replica**; SQLite and the bundled worker are not configured for multi-process orchestration.
5. Verify: `curl -fsS http://localhost:8000/api/health`.

## Targeted changes (original freight logic preserved)

- Copilot: browser speech-to-text microphone + optional text-to-speech readout. Browser permission and HTTPS/localhost required; may be unavailable in some browsers.
- Sign-in: role dropdown confirmed against stored assigned role, no role escalation.
- Lockout: backend error shown verbatim, not the frontend's `Session expired` fallback.
- Locked recovery: question visible and account-locked warning; answer/reset blocked until admin unlock.
- Removed unsafe default administrator password and require configured stable JWT secret.

## Tests

From this folder, install `pip install -r requirements.txt` and run `pytest -q tests`.

Tests verify actual API login, five failures → lock, recovery question visibility, blocked reset, admin unlock, role mismatch, Customer 403, existing freight pages, SQL Copilot, and voice controls in served JavaScript.

**Still requires real-environment testing:** browser microphone permission/recognition, actual SMTP OTP delivery, production HTTPS and proxy settings, external weather data reliability, performance under concurrent users, security review, and persistent backup/restore. Passing offline tests does not certify the service as production secure.

### Python 3.13 / ensurepip startup fix

The previously released Colab notebook could stop during runtime recovery while creating `/content/freightquote_env` because `venv.EnvBuilder(with_pip=True)` invoked `ensurepip` and failed. This version instead uses `sys.executable` and installs only missing libraries with `python -m pip`. Open the updated notebook, choose **Runtime → Restart session**, then **Run all**. You can also rerun the final launch cell alone after reset because it restores embedded sources and checks packages without virtualenv.
