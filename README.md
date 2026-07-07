# NGSign connector for Odoo

Integrates **NGSign** (electronic signature) into **Odoo Community 17.0**.

Send any PDF attachment (invoice, quotation, contract…) to NGSign, let the signer
sign (email invitation, link, or face to face), then automatically retrieve the
signed PDF and re-attach it to the source Odoo record.

## Package contents

```
ngsign-odoo-plugin/
├── addons/ngsign/                    ← the Odoo add-on
│   ├── __manifest__.py
│   ├── models/
│   │   ├── ngsign_client.py          ← thin NGSign API client (Odoo-free, testable)
│   │   ├── ngsign_transaction.py     ← tracking model + poll/retrieve + cron
│   │   └── res_config_settings.py    ← server URL + API token + defaults
│   ├── wizard/ngsign_send_wizard.py  ← "Send to NGSign" wizard
│   ├── data/ir_cron.xml              ← 5-min polling job
│   ├── views/ · security/ · static/
│   └── tests/test_ngsign_flow.py     ← E2E test against the mock (opt-in)
├── addons/ngsign_sale/               ← bridge: quotation (sale.order) signature
│   ├── models/sale_order.py          ← "Send for customer signature" + Refresh
│   └── views/sale_order_views.xml
├── docker/
│   ├── docker-compose.yml            ← db + odoo:17.0 + ngsign-mock
│   ├── odoo.conf
│   └── ngsign_mock/mock_server.py    ← in-memory NGSign API mock (stdlib only)
├── scripts/e2e_smoke.py              ← standalone contract test (no Odoo needed)
└── docs/
    ├── TECHNICAL_MANUAL.md           ← architecture, API mapping, flows, limits
    └── INSTALLATION.md               ← run the POC on Docker, step by step
```

## Documentation

| Guide | For |
|-------|-----|
| **[docs/INSTALLATION_PRODUCTION.md](docs/INSTALLATION_PRODUCTION.md)** | Installing on a **real, running Odoo** (native / Docker / odoo.sh) |
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Running the **local Docker POC** against the bundled mock |
| [docs/TECHNICAL_MANUAL.md](docs/TECHNICAL_MANUAL.md) | Architecture, API mapping, flows, limitations & roadmap |

## The only 2 required settings

In **Settings → NGSign**:
- **Server URL** — NGSign base URL, e.g. `https://sandbox.ng-sign.com`
  (for the local POC: `http://ngsign-mock:8080`).
- **API token** — Bearer token generated from the NGSign web app.

## Quick start (POC on Docker)

```bash
cd docker
docker compose up -d
# Odoo:  http://localhost:8069   (create a DB, install "NGSign Electronic Signature")
# Mock:  http://localhost:8090
```

Then follow **`docs/INSTALLATION.md`** for the full click-through and the two
automated validations (`scripts/e2e_smoke.py` and the Odoo test).

## Modules

- **`ngsign`** — core connector. Send any PDF attachment for signature, track it,
  retrieve the signed document. Depends on `base`, `mail`.
- **`ngsign_sale`** — Sales bridge. Adds **"Envoyer pour signature client"** on a
  quotation (generates the quotation PDF, prefills the customer as signer), a
  **waiting status badge** on the order, and a **"Rafraîchir la signature"** button
  that pulls the signed PDF back onto the order. Depends on `ngsign`, `sale`;
  auto-installs when both are present.
- **`ngsign_sale_management`** — Quotation-template bridge. Adds an **Electronic
  signature (NGSign)** section on quotation templates to set the customer
  signature position; a quotation created from the template uses that position
  automatically. Depends on `ngsign_sale`, `sale_management`; auto-installs when
  both are present. Without a template, the global NGSign position settings apply.

## How it maps to the NGSign API

| Step | NGSign web service | Client method |
|------|--------------------|---------------|
| Upload PDF | `POST /server/protected/transaction/pdfs` | `upload_pdf` |
| Configure + launch | `POST /server/protected/transaction/{id}/launch` | `launch` |
| Poll status | `GET /server/any/transaction/{id}` | `get_transaction` |
| Download signed PDF | `GET /server/any/transaction/{id}/pdfs/{doc}` | `download_pdf` |
| Cancel | `POST /server/protected/transaction/{id}/cancel` | `cancel` |

The client is a faithful Python transposition of the Maarch connector's
`NgsignClient.php` (same endpoints, same `{object, errorCode, message}` envelope,
same generous timeouts — the NGSign sandbox is slow).

## Status

Functional POC, validated end to end against the bundled mock. Sandbox validation
against a real NGSign instance is a config change (URL + token). See
`docs/TECHNICAL_MANUAL.md` for the productization roadmap and limitations.

## Requirements

- Odoo Community 17.0, Python `requests` (shipped with Odoo)
- An NGSign account with an API token and the "transaction" feature enabled.

Do not hesitate to contact NGSign (contact@ng-sign.com) or your NGSign integrator to get started.

## License

**GNU Lesser General Public License v3.0** (see `LICENSE`). LGPL-3 is the
Odoo-compatible choice for an add-on depending on Odoo Community (itself LGPL-3).

Copyright © 2026 NG Technologies.
