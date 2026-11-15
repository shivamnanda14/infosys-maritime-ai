# FreightQuote AI — Local release checks

Test environment: local Python runtime, FastAPI TestClient, temporary SQLite data, worker disabled for deterministic tests.

## Passed

- 26 application Python files compiled successfully.
- Browser JavaScript (`app/static/app.js`) passed `node --check` syntax validation.
- `pytest -q tests` passed: **4 tests** (health/assets/nine authenticated pages and Route AI calculation; role selector/Customer authorization; five-try lockout/locked security question/admin unlock; SQL Copilot and served browser voice controls).
- Notebook validated with `nbformat.validate`; the standalone recovery archive embedded inside the notebook contains the updated application sources and images.

## Not validated in this environment

- Real microphone dictation, browser microphone permissions and text-to-speech voices.
- Sending/receiving actual email OTPs through a configured SMTP provider.
- Running the entire Google Colab runtime or an external ngrok/public HTTPS tunnel.
- Building/starting the Docker image on a real container host.
- Production-load concurrency, external weather network behavior, penetration testing, backup restoration and continuous uptime.

FastAPI's `on_event` hooks generate deprecation warnings with recent versions; they are warnings, not failures in the test run.

This is an internship/demo deployment package with a tested local backend, not a certification that the service is production secure.
