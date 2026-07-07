# NGSign Odoo connector — Technical manual

## 1. Overview

The add-on lets Odoo push a PDF to NGSign, drive the signature transaction, and
re-integrate the signed document. It targets **generic PDF attachments**, so it
works on invoices, quotations, contracts, or any uploaded file, without depending
on Accounting or Sales.

## 2. Architecture

```
  Odoo record (any model)
        │  PDF attachment (ir.attachment)
        ▼
  ngsign.send.wizard ──upload_pdf──► NGSign  POST /server/protected/transaction/pdfs
        │             ──launch─────►         POST /server/protected/transaction/{id}/launch
        ▼
  ngsign.transaction  (status SENT/LAUNCHED, tracks tx uuid + doc identifier)
        │
   ir.cron (5 min)  ──get_transaction──► GET /server/any/transaction/{id}
        │   if SIGNED:
        │             ──download_pdf────► GET /server/any/transaction/{id}/pdfs/{doc}
        ▼
  signed ir.attachment re-attached to the source record + chatter note
```

Three layers, mirroring the Maarch connector:

| Layer | File | Responsibility |
|-------|------|----------------|
| Transport | `models/ngsign_client.py` | HTTP, Bearer auth, envelope, timeouts. **No Odoo import** → unit-testable, reused by `scripts/e2e_smoke.py`. |
| Domain | `models/ngsign_transaction.py` | Tracking record, poll/retrieve, cancel, cron. |
| UI | `wizard/ngsign_send_wizard.py` + `views/` | Send action, settings, transaction views. |

## 3. API mapping

The client is a faithful transposition of `NgsignClient.php`:

| Method | Verb + path | Notes |
|--------|-------------|-------|
| `upload_pdf` | `POST /server/protected/transaction/pdfs` | body = `[{fileName, fileExtension:"pdf", fileBase64}]` |
| `launch` | `POST /server/protected/transaction/{id}/launch` | body = `{sigConf:[...]}` |
| `get_transaction` | `GET /server/any/transaction/{id}` | status read from `object.status` |
| `download_pdf` | `GET /server/any/transaction/{id}/pdfs/{doc}` | returns raw PDF bytes |
| `cancel` | `POST /server/protected/transaction/{id}/cancel` | since NGSign 2.36 |

**Response envelope.** Success payloads are wrapped: `{object, errorCode, message}`.
`extract_upload_ids` reads `object.uuid` and `object.pdfs[0].identifier`;
`extract_status` reads `object.status`; both fall back gracefully if the envelope
is absent.

**Timeouts.** `(connect=30s, read=240s)` — the NGSign sandbox is slow; uploads can
exceed 80s. Same values as the Maarch connector.

**API prefix.** All paths are built as `{api_prefix}{path}`, with `api_prefix`
defaulting to `/server` and configurable via *Settings → NGSign → API base path*
(`ngsign.api_base_path`). The connector reads it once in
`ngsign.transaction._get_client()`, the single place clients are built (the wizard
reuses it), so URL, token and prefix have one source of truth.

## 4. The `sigConf` payload

Built in `ngsign_send_wizard.action_send`:

```json
[{
  "signer": {"firstName": "...", "lastName": "...", "email": "...", "phoneNumber": ""},
  "sigType": "CERTIFIED_TIMESTAMP",
  "choosePosition": true,
  "docsConfigs": [{"documentName": "...", "documentExtension": "pdf", "identifier": "<doc>"}],
  "mode": "BY_MAIL",
  "otp": "NONE"
}]
```

- `choosePosition`: driven by *Settings → NGSign → Signature position*
  (`ngsign.choose_position`, **default off**). When off, the connector sends a
  fixed `page/xAxis/yAxis` (from `ngsign.default_page/_x/_y`) so the signer does
  **not** place the stamp — the intended behaviour for customer-facing flows like
  quotation signature. When on, no position is sent and the signer places it on
  the NGSign page. The wizard defaults from these settings (a caller can override
  per request via `default_choose_position` / `default_page` / `default_x_axis` /
  `default_y_axis` in the context).
- Signature **types**: `LATER`, `CERTIFIED_TIMESTAMP`, `SIGNATURE_WITH_SSCD`,
  `REMOTE_SIGN`, `DIGI_GO`, `MOBILE_ID`.
- Signature **modes**: `BY_MAIL` (email invitation), `BY_LINK` (caller redirects
  the signer, using `signing_url` computed on the transaction), `FACE_TO_FACE`.
- **OTP**: `NONE`, `OTP` (SMS), `EMAIL`.

## 5. Signature modes and redirection

- **BY_MAIL** — NGSign emails the signer. Odoo just polls. Simplest, fully
  automated. Default for the POC.
- **BY_LINK / FACE_TO_FACE** — the transaction exposes `signing_url`:
  `https://{server}/pds/#/transaction/sign/{nextSigner}?uuid={uuid}`. The caller
  redirects the signer there (e.g. a portal button — not built in this POC).

## 6. Retrieval logic

`ngsign.transaction._poll_one` (called by the cron and the manual buttons):
- status ∈ {SIGNED, COMPLETED, FINISHED, VALIDATED, DONE} → download + attach +
  chatter, set **SIGNED**;
- status ∈ {REJECTED, REFUSED, CANCELLED, CANCELED, EXPIRED} → set the matching
  closed status;
- otherwise → keep pending (SENT → LAUNCHED on first poll).

The tolerant state sets are copied from the Maarch connector so the behaviour is
identical across both integrations.

## 7. Data model — `ngsign.transaction`

Equivalent to the Maarch `ngsign_transactions` table, Odoo-native:
`name` (tx uuid), `document_identifier`, `status`, `res_model`/`res_id`,
`source_attachment_id`, `signed_attachment_id`, signer fields, `sig_type`, `mode`,
`next_signer`, `signing_url` (computed), `last_error`. Inherits `mail.thread` for
status tracking + chatter.

## 8. The POC mock

`docker/ngsign_mock/mock_server.py` — stdlib-only in-memory implementation of the
five endpoints, faithful to the envelope, plus test helpers
(`POST /_mock/sign/{uuid}`, `/_mock/reject/{uuid}`, `GET /_mock/state`). It exists
so the whole cycle is validated **deterministically and offline**; the real
sandbox is a config switch away. Download returns the originally uploaded bytes, so
the "signed" PDF is always a valid PDF.

## 9. Validation performed

1. `scripts/e2e_smoke.py` — client ↔ API contract, no Odoo (fast, CI-friendly).
2. `addons/ngsign/tests/test_ngsign_flow.py` — full Odoo cycle against the mock
   (wizard → transaction → simulate sign → poll → signed attachment). Opt-in via
   `NGSIGN_TEST_URL`.
3. Manual UI walkthrough — see `docs/INSTALLATION.md`.

## 10. Limitations & productization roadmap

Known POC limitations (not blockers, but to address before production):

- **Single signer** per document in the wizard. NGSign supports multi-signer /
  parallel / ordered flows (`sigConf` is already a list) — expose several signers
  in the wizard and store them.
- **One PDF per send.** Multi-document transactions are supported by the API; batch
  several attachments into one transaction.
- **Polling only.** NGSign supports a `callbackUrl` (webhook) for
  authorized domains — add a controller endpoint to react on sign/refuse instead of
  a 5-min cron.
- **No signer directory integration.** Signer identity is typed in the wizard;
  wire it to `res.partner` / `res.users` for one-click selection.
- **`BY_LINK` redirect** is exposed as a URL but no portal button is shipped.
- **Secrets.** The API token is stored as an `ir.config_parameter`; consider a
  vault / per-company token for multi-company setups.
- **Invoice / FATOORA angle.** A follow-up module can add a "Sign & submit"
  button directly on `account.move` to combine signature with TTN e-invoicing.
- **Error surfacing.** Failures are logged and stored in `last_error`; add
  user-facing activities/notifications for stuck transactions.
- **Tests.** Add unit tests with a mocked `requests` layer for CI without the
  compose stack, and negative-path tests (reject/expire/cancel).
