# FreightQuote AI — Milestone 2

**Infosys Springboard Internship 7.0 · Batch 4 · Team 02**

FreightQuote AI is an ocean-freight workspace for building quotations, comparing carriers, reviewing routes, checking weather and customs requirements, and asking **database-grounded** questions through a SQL Copilot. Milestone 2 extends the provided freight application with **secure accounts, five user roles, profiles, administration, an improved SQL Copilot and a consistent interface**.

> **What was provided versus added:** The original reference notebook already contained the six freight agents, a basic SQL Copilot, FastAPI and freight data. This milestone integrates Milestone 1 authentication and introduces multi-user controls, RBAC, account management, profiles, Copilot question coverage and interface improvements. It does not claim to have created the six agents from scratch.

## Quick navigation

[Features](#features) · [Role permissions](#role-permissions) · [Screenshots](#real-website-screenshots) · [Run in Colab](#run-in-google-colab) · [Run with Docker](#run-with-docker) · [Contributors](#team-contributions)

## Features

| Area | How it works |
|---|---|
| **Accounts** | Customer self-registration, bcrypt password hashes, six-digit email verification, strong password checks and JWT sessions. Public registration does **not** grant privileged roles. |
| **Recovery & lockout** | Password recovery by email OTP or security question. After five failed sign-ins, an administrator must unlock the account. OTP requests are rate-limited. |
| **Profiles** | View role, email, join date and recent login. Change username or password after current-password validation. |
| **Five-role RBAC** | Server-side access permissions for Admin, Operations Manager, Freight Broker, Auditor and Customer; denied requests receive HTTP 403. |
| **Admin console** | Provision users, assign or update roles, link customer records, lock/unlock accounts and review activity logs. |
| **SQL Copilot** | Natural-language-style freight question patterns execute **predefined/parameterized SQL**, returning exact database rows and the query/row count. It is not a general-purpose LLM and does not answer every question. |
| **Voice controls** | Browser microphone dictation for asking questions and optional text-to-speech for answers, subject to browser permissions/support. |
| **Freight agents** | Existing Route AI, Spot Quotes, Carriers, Weather Risk, Margin and Customs modules remain in the integrated application. |
| **Theme** | Consistent light/dark design and role-specific navigation. |

### The freight workflow

1. A permitted user selects an origin/destination, cargo, weight, HS code and customer.
2. The existing quote pipeline evaluates the route, weather, carrier and pricing, then customs/documentation and approval conditions.
3. The quote page shows price, margin, ETA, status and (where available) an agent trace or generated documents.
4. Authorized users investigate holds or supporting data in the related modules.

**Data provenance:** The Weather Risk UI identifies **Open-Meteo weather/marine information** as live/cached, but **vessel positions are simulated** and **congestion is model-predicted** unless a real data source is connected. The *Inject Storm* control is a test scenario, not a verified storm. Illustrative quotes on the public landing page are not commercial offers.

## Role permissions

| Role | Copilot | Route | Quotes | Carriers | Weather | Margin | Customs | Run agents | Manage users |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Admin | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Operations Manager | ✓ | ✓ | — | ✓ | ✓ | — | ✓ | ✓ | — |
| Freight Broker | ✓ | — | ✓ | ✓ | — | ✓ | — | — | — |
| Auditor (read-only) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — |
| Customer (scoped) | ✓ | — | **Own** | — | — | — | — | — | — |

The administrator assigns roles; the role selected on the **sign-in form is checked against the account's existing assignment**, not used to grant a new role. Customers cannot view other customers' quotes or unrestricted SQL results. Auditor review screens may show document controls, but the server-side permission checks determine which mutations are allowed.

## Real website screenshots

These are the **50 supplied screenshots from 6 November 2026**, grouped into short, expandable sections to keep the README practical. **Visible email addresses, selected account identifiers, test OTP values and administrative email records are redacted** in the public images; the original screenshots are not shipped. Numeric dashboard values are snapshots of a demo and may change between runs.

<details>
<summary><strong>Landing page</strong> — 7 screenshots (click to expand)</summary>

**01. Landing — hero** — The public homepage introduces the platform and provides Login/Create Account navigation.

![Landing — hero](screenshots/01_landing_hero.webp)

**02. Landing — quote illustration** — A clearly labelled illustrative quote explains how routing, carrier selection, cost and margin can contribute to a quote. Figures shown are demo values.

![Landing — quote illustration](screenshots/02_landing_quote_illustration.webp)

**03. Landing — feature cards** — Feature cards introduce the SQL Copilot and the six operations modules: routing, quotes, carriers, weather, margin and customs.

![Landing — feature cards](screenshots/03_landing_feature_cards.webp)

**04. Landing — four-step journey** — The visitor workflow is summarized as entering requirements, agent review, pricing and reviewing a quote.

![Landing — four-step journey](screenshots/04_landing_four_step_journey.webp)

**05. Landing — target users** — Freight forwarders, shippers/exporters and analysts are shown as three audiences for the platform.

![Landing — target users](screenshots/05_landing_target_users.webp)

**06. Landing — security** — Highlights bcrypt password hashes, signed JWT sessions and email verification. Passwords are hashed, not reversibly encrypted.

![Landing — security](screenshots/06_landing_security.webp)

**07. Landing — FAQ** — Frequently asked questions clarify basic use, roles, recovery and account creation before visitors sign in.

![Landing — FAQ](screenshots/07_landing_faq.webp)

</details>

<details>
<summary><strong>Authentication and security</strong> — 7 screenshots (click to expand)</summary>

**08. Sign-in — assigned role** — Sign-in accepts username or email, the administrator-assigned role and password. Choosing a role does not assign or elevate permissions.

![Sign-in — assigned role](screenshots/08_sign_in_assigned_role.webp)

**45. Registration — customer** — Public self-registration collects username, email, strong password and security question/answer. New accounts are Customers by default.

![Registration — customer](screenshots/45_registration_customer.webp)

**46. Registration — email verification** — A six-digit email code verifies a new account before first sign-in. The example email is redacted.

![Registration — email verification](screenshots/46_registration_email_verification.webp)

**47. Recovery — email OTP** — Forgot-password supports time-limited email OTP recovery and resend throttling; the example email is redacted.

![Recovery — email OTP](screenshots/47_recovery_email_otp.webp)

**48. Recovery — security question** — The alternative recovery path displays the saved question and checks the answer without revealing it. The account identifier is redacted.

![Recovery — security question](screenshots/48_recovery_security_question.webp)

**49. Recovery — rate limiting** — Rate limiting protects repeated OTP attempts; the submitted email and test code are redacted.

![Recovery — rate limiting](screenshots/49_recovery_rate_limiting.webp)

**50. Locked account — clear error** — Locked users receive the explicit account-locked message rather than a misleading session-expired error. The login identifier is redacted.

![Locked account — clear error](screenshots/50_locked_account_clear_error.webp)

</details>

<details>
<summary><strong>SQL Copilot</strong> — 3 screenshots (click to expand)</summary>

**09. Copilot — example prompts** — The administrator-facing Copilot shows suggested freight questions, a text field and a microphone input button.

![Copilot — example prompts](screenshots/09_copilot_example_prompts.webp)

**13. Copilot — SQL answers** — Examples show a zero-row carrier lookup and a weather query with visible SQL/row counts and optional text-to-speech.

![Copilot — SQL answers](screenshots/13_copilot_sql_answers.webp)

**30. Customer — scoped Copilot** — Customer prompts focus on that customer’s shipments, recent quotes and cargo location; answers must respect account scope.

![Customer — scoped Copilot](screenshots/30_customer_scoped_copilot.webp)

</details>

<details>
<summary><strong>Freight agents</strong> — 14 screenshots (click to expand)</summary>

**10. Route AI — fleet map** — A route analysis page displays ports, vessels, congestion and storm indicators on the world map.

![Route AI — fleet map](screenshots/10_route_ai_fleet_map.webp)

**11. Route AI — route planner** — The planner accepts origin, destination and cargo; Plan Route computes options using the existing routing system.

![Route AI — route planner](screenshots/11_route_ai_route_planner.webp)

**12. Spot Quotes — new quote** — An authorized operator selects origin, destination, cargo, weight, HS code and customer for the quote pipeline.

![Spot Quotes — new quote](screenshots/12_spot_quotes_new_quote.webp)

**14. Spot Quotes — results** — After quoting, the module displays quote counts and statuses, including approved and on-hold records.

![Spot Quotes — results](screenshots/14_spot_quotes_results.webp)

**15. Spot Quotes — history and tickets** — Users can review recent quotes and open tickets describing holds that need attention.

![Spot Quotes — history and tickets](screenshots/15_spot_quotes_history_and_tickets.webp)

**16. Carriers — ranking** — The carrier league table compares scores, on-time performance, cost index, risk and shipment counts.

![Carriers — ranking](screenshots/16_carriers_ranking.webp)

**17. Weather Risk — overview** — The module summarizes weather provider freshness, monitored ports, storms and vessel/port risk.

![Weather Risk — overview](screenshots/17_weather_risk_overview.webp)

**18. Weather Risk — world map** — Interactive weather and maritime markers are color-coded by wind and storm risk.

![Weather Risk — world map](screenshots/18_weather_risk_world_map.webp)

**19. Weather Risk — data sources** — Port weather is sourced from Open-Meteo; the page distinguishes that feed from simulated vessel positions and modeled congestion.

![Weather Risk — data sources](screenshots/19_weather_risk_data_sources.webp)

**20. Weather Risk — storm test** — Inject Storm adds a *simulation* for testing reroute behavior; it is not a real weather alert.

![Weather Risk — storm test](screenshots/20_weather_risk_storm_test.webp)

**21. Margin — overview** — Pricing totals and thresholds show average margin, low-margin quotes, high-value quotes and revenue represented in quotes.

![Margin — overview](screenshots/21_margin_overview.webp)

**22. Margin — cost build-up** — The chosen quote is broken into base cost, fuel, customs, insurance, margin and total, with an accompanying chart.

![Margin — cost build-up](screenshots/22_margin_cost_build_up.webp)

**23. Customs — held shipments** — Customs shows active rules and a list of shipments or quotes on hold because documents are missing.

![Customs — held shipments](screenshots/23_customs_held_shipments.webp)

**24. Customs — rules and documents** — HS-chapter rules identify required documents; the attachment UI supports submitting relevant documents against a hold.

![Customs — rules and documents](screenshots/24_customs_rules_and_documents.webp)

</details>

<details>
<summary><strong>Profiles and role-specific views</strong> — 16 screenshots (click to expand)</summary>

**25. Profile — admin summary** — The administrator profile displays role, joined date and last login, as well as an authenticated username-change form.

![Profile — admin summary](screenshots/25_profile_admin_summary.webp)

**26. Profile — credential update** — Profile security settings permit password changes after confirmation of the current password.

![Profile — credential update](screenshots/26_profile_credential_update.webp)

**31. Customer — My Quotes** — Customers see only linked quote records and corresponding statuses in the My Quotes view.

![Customer — My Quotes](screenshots/31_customer_my_quotes.webp)

**32. Customer — profile** — A Customer profile shows its assigned customer identifier and account settings. Personal email is redacted.

![Customer — profile](screenshots/32_customer_profile.webp)

**33. Freight Broker — carriers** — Freight Broker access includes carrier comparison and risk metrics, without admin controls.

![Freight Broker — carriers](screenshots/33_freight_broker_carriers.webp)

**34. Freight Broker — margins** — Freight Broker can review pricing breakdowns and profit-margin information according to its role permissions.

![Freight Broker — margins](screenshots/34_freight_broker_margins.webp)

**35. Freight Broker — profile** — The profile reflects the assigned Freight Broker role. Personal email is redacted.

![Freight Broker — profile](screenshots/35_freight_broker_profile.webp)

**36. Freight Broker — quotations** — The freight quotation entry form is available to the Freight Broker with a role-appropriate sidebar.

![Freight Broker — quotations](screenshots/36_freight_broker_quotations.webp)

**37. Operations Manager — route** — Operations Manager sees Route AI and can examine the modeled congestion and live-fleet view.

![Operations Manager — route](screenshots/37_operations_manager_route.webp)

**38. Operations Manager — weather** — The operations-focused Weather Risk view includes port and storm information without pricing screens.

![Operations Manager — weather](screenshots/38_operations_manager_weather.webp)

**39. Operations Manager — customs** — Customs review is available in Operations Manager’s navigation, with customs rule and held-shipment data.

![Operations Manager — customs](screenshots/39_operations_manager_customs.webp)

**40. Operations Manager — profile** — The profile confirms Operations Manager access and supports username/password maintenance. Personal email is redacted.

![Operations Manager — profile](screenshots/40_operations_manager_profile.webp)

**41. Auditor — route view** — Auditor can inspect route data without a Run Analysis action, illustrating read-only access.

![Auditor — route view](screenshots/41_auditor_route_view.webp)

**42. Auditor — customs view** — Auditor sees customs status and document requirements for review purposes.

![Auditor — customs view](screenshots/42_auditor_customs_view.webp)

**43. Auditor — documents** — The document tab lists generated PDFs and an upload/extraction interface; authorization still controls whether actions are accepted.

![Auditor — documents](screenshots/43_auditor_documents.webp)

**44. Auditor — profile** — An Auditor account is labelled read-only in the access model; profile credentials can still be maintained. Personal email is redacted.

![Auditor — profile](screenshots/44_auditor_profile.webp)

</details>

<details>
<summary><strong>Administration and RBAC</strong> — 3 screenshots (click to expand)</summary>

**27. Admin — account statistics** — The Admin Dashboard summarizes total, active and locked accounts, and provides a create-user form with role assignment.

![Admin — account statistics](screenshots/27_admin_account_statistics.webp)

**28. Admin — account management** — The user table contains role, state, customer mapping and login metadata with controls for permitted management actions. Email column is redacted.

![Admin — account management](screenshots/28_admin_account_management.webp)

**29. Admin — audit log and role matrix** — The audit log records administrative events; the role matrix shows per-module permissions. Email fragments are redacted.

![Admin — audit log and role matrix](screenshots/29_admin_audit_log_and_role_matrix.webp)

</details>

## How to run it

### Run in Google Colab

1. Open **`FreightQuote_AI_Milestone2_Final_Deployment.ipynb`** in Google Colab.
2. Add `JWT_SECRET` (a strong random secret) and `ADMIN_PASSWORD` to Colab **Secrets**. Add `EMAIL_ADDRESS` and `EMAIL_PASSWORD` for live email verification; these should be an application password/SMTP credentials, **not** credentials placed in code.
3. Run the notebook top to bottom. The fixed startup uses Colab's existing Python environment rather than creating an `ensurepip` virtual environment.
4. Open the notebook's displayed application URL. Complete the customer account verification flow, or sign in using an administrator account initialized from your own secure settings.
5. If a runtime reset occurs, rerun the notebook's recovery/startup cells. **Colab runtime storage is temporary** unless you explicitly configure persistence.

**Never commit secrets, token files, SQLite databases with real users, or Colab output logs to GitHub.** See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for full notes.

### Run with Docker

```bash
cp .env.example .env
# Fill in strong JWT_SECRET and ADMIN_PASSWORD in .env; add SMTP credentials if needed.
docker compose up --build
```

See `compose.yaml`, `Dockerfile`, `requirements.txt`, `.env.example`, and `DEPLOYMENT_GUIDE.md`. Confirm host/port and secrets in your deployment environment before publishing a public endpoint. Docker is an alternative packaging path; the final demonstration was run from the notebook.

### Repository layout

```text
README.md                   This guide and complete screenshot gallery
FreightQuote_AI_Milestone2_Final_Deployment.ipynb
app/                        FastAPI, database, authentication, RBAC, Copilot, agents and static UI
app/static/                 Landing page, CSS/JS, images and offline vendor assets
screenshots/                50 redacted website screenshots + manifest
tests/                      Included application tests
requirements.txt            Python dependencies
Dockerfile / compose.yaml   Container configuration
DEPLOYMENT_GUIDE.md         Deployment and environment setup
TEST_RESULTS.md             Existing local test notes
.env.example / .gitignore   Configuration example / exclusion of local secrets
```

## Validation and limitations

- The updated notebook includes the earlier **Colab Python 3.13 / `ensurepip` startup fix**.
- Role checks must be enforced on the backend, not just by hiding sidebar buttons. Incorrectly selected sign-in roles are not a way to acquire permissions.
- The Copilot uses **freight-specific SQL patterns** with graceful handling for unsupported questions or empty results. Speech recognition depends on browser support and microphone permission.
- External weather feeds, SMTP, public tunnel URLs and actual Colab/Docker runtime behavior require separate live verification before production use.
- The application is an internship prototype; do not assume commercial availability, complete production hardening, or real AIS tracking.
- If the app shows a quote lookup with zero rows, it means no matching records were available under the query criteria; it is not evidence of a fabricated answer.

For checks, see [TEST_RESULTS.md](TEST_RESULTS.md) and `tests/test_release.py`.

## Team contributions

| Collaborator | Contribution to Milestone 2 |
|---|---|
| **Tirth Thakkar** | Integrated the Milestone 1 landing page into Aparna's codebase, improved the UI and ensured consistent role-specific styling. |
| **Alisetti Ranga Triveni** | Built the Profile page, including edit flows, validation, saved changes and agreed role-specific views. |
| **Aparna Pulimoottil Jaykumar** | Completed the Admin Dashboard and implemented server-side RBAC enforcement across all five roles. |
| **Shivam Kumar** | Fine-tuned the SQL Copilot, connected the relevant data and handled errors, empty results and unsupported questions. |

**Attribution:** The six original freight agents and initial SQL Copilot are inherited from the Milestone 2 reference project. Team contributions above describe enhancements and integrations, not ownership of the original baseline.

## GitHub submission

**Extract `Milestone 2.zip` and upload the extracted files/folders to the root of your GitHub repository.** GitHub does *not* automatically unpack a dragged-and-dropped ZIP; uploading the ZIP alone will not render this README or its screenshots. On GitHub, the screenshots are embedded from relative paths so the gallery opens correctly.

*Milestone 2 · Team 02 · Infosys Springboard Internship 7.0.*
