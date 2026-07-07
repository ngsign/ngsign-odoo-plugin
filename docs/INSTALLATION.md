# POC installation & validation (Docker)

This walks through running the NGSign Odoo plugin locally and validating the full
signature cycle against the bundled **mock** NGSign server — no real NGSign
account needed. Switching to a real sandbox is a two-field config change at the end.

> Installing on a **real, already-running Odoo** instead? See
> **[`INSTALLATION_PRODUCTION.md`](INSTALLATION_PRODUCTION.md)**. This page is the
> local Docker POC only.

## 0. Prerequisites

- Docker + Docker Compose
- Ports free: `8069` (Odoo), `8090` (mock)

## 1. Start the stack

```bash
cd docker
docker compose up -d
docker compose ps          # db, ngsign-mock, odoo should be up
docker compose logs -f odoo   # wait for "HTTP service (werkzeug) running"
```

- Odoo: <http://localhost:8069>
- Mock health: <http://localhost:8090/> → `{"service":"ngsign-mock",...}`

## 2. Fast automated check (no Odoo, ~1s)

Proves the client ↔ API contract end to end (upload → launch → sign → download):

```bash
python3 scripts/e2e_smoke.py --url http://localhost:8090
# expect: ALL CHECKS PASSED  (exit code 0)
```

## 3. Create the Odoo database & install the module

1. Open <http://localhost:8069>, create a database (master password `admin`,
   set an admin login/password, **uncheck** "Load demo data" if you want a clean DB).
2. Go to **Apps** → *Update Apps List* (menu shows in developer mode) → search
   **NGSign** → **Install** "NGSign Electronic Signature".
   - To enable developer mode: **Settings → scroll down → Activate the developer tools**.

## 4. Configure NGSign (point at the mock)

**Settings → NGSign**:
- **Server URL**: `http://ngsign-mock:8080`  ← the mock, reachable on the compose network
- **API token**: `test-token` (any non-empty value)
- Save.

> Note: from inside the Odoo container the mock is `ngsign-mock:8080`; from your
> host it's `localhost:8090`. Odoo must use the `ngsign-mock:8080` form.

## 5. Send a document for signature

1. **NGSign → New Signature**.
2. Upload any PDF (or pick an existing PDF attachment), fill the signer
   (first name, last name, email), keep **Signature type = Simple signature**,
   **Mode = By email invitation**.
3. **Send for signature** → you land on the created **NGSign Transaction**
   (status **Sent**).

## 6. Simulate the signature and retrieve the signed PDF

Two ways to mark the document as signed on the mock:

- **From Odoo (easiest):** on the transaction, click **Simulate signature (mock)**.
  It calls the mock, then polls → status flips to **Signed** and the **Signed PDF**
  field is filled.
- **From the host (CLI):**
  ```bash
  # get the transaction UUID from the form, then:
  curl -X POST http://localhost:8090/_mock/sign/<TX_UUID> -H "Authorization: Bearer test-token"
  ```
  Then on the transaction click **Poll status now** (or wait for the 5-min cron).

**Expected result:** status **Signed**, a `SIGNED_*.pdf` attachment created, and a
chatter note on the source record (if the PDF was attached to one).

## 7. (Optional) Run the Odoo integration test

```bash
docker compose exec -e NGSIGN_TEST_URL=http://ngsign-mock:8080 odoo \
  odoo -d <YOUR_DB> -i ngsign --test-enable --test-tags /ngsign --stop-after-init
```
Look for the test `TestNgsignFlow.test_full_signature_cycle` passing.

## 8. Switch to a real NGSign sandbox

Only **Settings → NGSign** changes:
- **Server URL**: your real NGSign base URL (e.g. `https://sandbox.ng-sign.com`)
- **API token**: a real Bearer token from the NGSign web app.

Then repeat steps 5–6, but sign for real via the NGSign email/link instead of the
mock helper. The **Simulate signature (mock)** button is a no-op against a real
server (it will report the mock endpoint is unavailable) — use the real signing
page.

## Teardown

```bash
docker compose down          # keep volumes
docker compose down -v       # wipe DB + Odoo data
```

## Troubleshooting

- **Module not in Apps list** → activate developer mode, *Update Apps List*.
- **"NGSign is not configured"** → set URL + token in Settings → NGSign.
- **Status stays "Sent"** → you haven't signed yet; use step 6. Check
  `docker compose logs ngsign-mock` and the transaction's **Last error** field.
- **Odoo can't reach the mock** → the URL must be `http://ngsign-mock:8080`
  (container network), not `localhost`.
