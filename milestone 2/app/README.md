# FreightQuote AI — Milestone 2

A multi-user freight workspace built with FastAPI, SQLite, JWT, five-role RBAC, the six freight agents and a SQL-based Copilot. The application is intended to run in Google Colab for the internship demonstration.

## Run in Google Colab

1. Upload `FreightQuote_AI_Milestone2_Final_Deployment.ipynb` to Colab. Use a CPU runtime.
2. In **Secrets**, add `JWT_SECRET` (at least 32 characters; stable across restarts) and a strong `ADMIN_PASSWORD` (12–72 UTF-8 bytes). For email OTP, add `EMAIL_ADDRESS` and `EMAIL_PASSWORD` (a supported SMTP app password). Optionally add `ADMIN_EMAIL` and `NGROK_AUTHTOKEN`.
3. Select **Runtime → Run all** and open the link printed by the final cell.
4. Sign in with the configured administrator username (`admin` by default) and `ADMIN_PASSWORD`. Change or securely rotate initial credentials before sharing access.
5. Use Administration to create internal-role accounts. Public signup creates only Customer accounts. To show account-specific quotes, link the Customer to the correct `customer_id` as an administrator.

## Latest targeted fixes

- **Copilot voice:** Press **🎤 Speak**, allow microphone permission in Chrome/Edge on HTTPS or localhost, review the recognized text, then press Ask Copilot. The optional **🔊 Read answer** button reads a result aloud. If the browser does not support speech recognition, the typed question continues to work. Speech recognition may use the browser/provider's speech service; do not dictate confidential content without checking your organization's privacy policy.
- **Locked-account sign-in:** The exact server error, **Account locked. Contact the administrator to unlock it**, is displayed instead of the generic session-expired message.
- **Security-question recovery:** A locked user can still view their configured question and a clear lock notice, but cannot verify an answer or reset the password until an administrator unlocks the account.
- **Sign-in role:** The login form provides a role selector; it must match the role already assigned by an administrator. Choosing a role cannot grant or change permissions. Public signup remains Customer-only.
- **Security prerequisites:** There are no published default administrator passwords; JWT_SECRET and ADMIN_PASSWORD must be configured before launching.

## Permission matrix

| Role | Copilot | Route | Quotes | Carriers | Weather | Margin | Customs | Run agents | Manage users |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Admin | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Operations Manager | ✓ | ✓ | — | ✓ | ✓ | — | ✓ | ✓ | — |
| Freight Broker | ✓ | — | ✓ | ✓ | — | ✓ | — | — | — |
| Auditor | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — |
| Customer | ✓ | — | Own only | — | — | — | — | — | — |

Permissions are enforced on the server, not merely by hiding navigation. Customer-facing quote data and relevant Copilot queries must be scoped to the linked customer account.

## Copilot examples to verify against the seeded dataset

- Which carrier is cheapest to Rotterdam?
- Which shipments have a high delay risk?
- Which shipments are on customs hold?
- Which ports are most congested?
- Show quotes with low margins.
- Show recent agent runs.
- Which carriers have the lowest on-time percentage?

Results must be obtained from the actual SQLite database. The engine includes 17 SQL query definitions and role-specific access checks. Record the live response, SQL statement, and row count during submission testing; sample records can change, so this README does not invent answers.

## Release validation checklist

Run `python -m pytest -q tests` from the release folder after installing dependencies. Live microphone capture, email delivery and Colab tunnel access must additionally be tested in your own browser and configured runtime; they cannot be fully validated by offline tests.

## Submission validation checklist

- Login, signup, forgot password with OTP and security question, Profile username and password updates
- Five test accounts, one per role; permitted and forbidden page/action requests (403)
- Admin create, role change, lock/unlock, delete, last-Admin protection, activity log
- Linked Customer sees only their own quotes
- Copilot query displays SQL and number of rows and enforces role scoping
- Run a quote through the seven-step pipeline, weather page after an injected storm, and verify background cycles
- Capture genuine screenshots of signup, login, Profile, Admin, allowed/denied cases, Copilot, quotes and weather
- Confirm no keys, tokens or databases are committed

## Deployment considerations

Colab sessions and `/content` storage are temporary; for continuous production hosting, migrate to a durable database and storage volume, deploy behind HTTPS, configure trusted proxy handling, secure SMTP, backups, logging, health checks, and an independent full end-to-end test. Seed records are demonstration data and must not be used as verified commercial quotations or authoritative customs guidance.

## Design

The landing-page sections and ship image are restored from the approved teammate design. A separate ocean-freight image is used for the responsive login and registration experience. The workspace uses a consistent maritime palette and offers light/dark appearance controls.
