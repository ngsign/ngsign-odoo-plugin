# Installing NGSign on an existing (production) Odoo

This guide installs the connector on a **running Odoo 17.0** instance. For a
throwaway local trial, use the Docker POC instead (`docs/INSTALLATION.md`).

> **Golden rule:** install and test on a **staging copy first**, and take a full
> backup (database + filestore) before touching production.

---

## 1. Compatibility & prerequisites

| Item | Requirement |
|------|-------------|
| Odoo | **17.0** Community or Enterprise |
| Python | `requests` — already bundled with Odoo, nothing to install |
| PDF engine | `wkhtmltopdf` — only for **`ngsign_sale`** (quotation PDF); standard in Odoo installs |
| NGSign | An account with the **transaction** feature enabled and an **API token** |
| Access | Ability to add custom add-ons (file/shell access, Docker, or odoo.sh) |

**Not supported:** Odoo Online / SaaS (`*.odoo.com`) — it does not allow custom
modules. Use self-hosted, Docker, or odoo.sh.

**Which modules do you need?**
- `ngsign` — core. Sign any PDF attachment. **Always required.**
- `ngsign_sale` — optional bridge for **Sales** (quotation signature). Depends on
  `ngsign` + `sale`; auto-installs when both are present.

---

## 2. Get the modules

Copy the two folders from this repository's `addons/` directory:

```
addons/ngsign/         → the core module
addons/ngsign_sale/    → the Sales bridge (optional)
```

Either `git clone` this repo on the server, or copy the folders by any means
(scp, CI artifact, etc.). Keep each module's folder structure intact
(`ngsign/__manifest__.py`, …).

---

## 3. Place them in an add-ons directory

Pick the section matching your deployment.

### A. Native install (systemd / source)

1. Copy the modules into a **custom add-ons directory**, e.g.:
   ```bash
   sudo mkdir -p /opt/odoo/custom-addons
   sudo cp -r ngsign ngsign_sale /opt/odoo/custom-addons/
   sudo chown -R odoo:odoo /opt/odoo/custom-addons
   ```
2. Add that directory to `addons_path` in `/etc/odoo/odoo.conf` (comma-separated,
   keep the existing paths):
   ```ini
   [options]
   addons_path = /opt/odoo/custom-addons,/usr/lib/python3/dist-packages/odoo/addons
   max_cron_threads = 2      ; must be >= 1 so the polling cron runs
   ```
3. Restart the service:
   ```bash
   sudo systemctl restart odoo
   ```

### B. Docker / docker-compose (production)

Mount the modules into a directory that is on `addons_path` (commonly
`/mnt/extra-addons`), **or** bake them into a custom image.

- **Volume (no rebuild):**
  ```yaml
  services:
    odoo:
      image: odoo:17.0
      volumes:
        - ./addons:/mnt/extra-addons:ro     # contains ngsign/ and ngsign_sale/
        - ./odoo.conf:/etc/odoo/odoo.conf:ro
  ```
  Ensure `addons_path` in `odoo.conf` includes `/mnt/extra-addons`.

- **Baked image (recommended for prod):**
  ```dockerfile
  FROM odoo:17.0
  COPY ngsign        /mnt/extra-addons/ngsign
  COPY ngsign_sale   /mnt/extra-addons/ngsign_sale
  ```

Then `docker compose up -d` (or redeploy the image).

### C. odoo.sh

Add the two module folders to your **odoo.sh Git repository** (repo root or a
scanned sub-folder), commit and push. odoo.sh rebuilds the branch and the modules
become installable from **Apps**.

---

## 4. Install the module(s)

**From the UI:**
1. Enable developer mode: *Settings → Developer Tools → Activate the developer mode*.
2. *Apps → Update Apps List* (top menu, dev mode only) → confirm.
3. Search **NGSign** → **Install** "NGSign Electronic Signature".
4. If **Sales** is installed, "NGSign for Sales" auto-installs. Otherwise install it
   later — it activates automatically once `sale` is present.

**From the command line (equivalent):**
```bash
# native
odoo -c /etc/odoo/odoo.conf -d <DB> -i ngsign,ngsign_sale --stop-after-init
sudo systemctl restart odoo

# docker
docker compose exec odoo odoo -d <DB> -i ngsign,ngsign_sale --stop-after-init
docker compose restart odoo
```
> After a CLI install/upgrade, **restart** the live server so its workers reload
> the registry and views.

---

## 5. Configure the connection

*Settings → NGSign*:

| Setting | Value |
|---------|-------|
| **Server URL** | NGSign platform base URL from NG Technologies, e.g. `https://sign.yourdomain.tn` |
| **API Token** | Bearer token generated in the NGSign web app (regenerating invalidates old tokens) |
| **API base path** | API context path. Default **`/server`** — change only if your instance differs (empty for none) |
| **Default signature type / mode** | Sensible defaults for new requests (e.g. `CERTIFIED_TIMESTAMP`, `BY_MAIL`) |
| **Signature position** | *Let the signer place the signature* is **off by default**: the visible signature is placed automatically at the configured **Page / X / Y**, so signers (e.g. your customers on a quotation) just sign without placing a stamp. Tune the coordinates to your document layout. |

> ⚠ **Base URL / API base path — verify with your NGSign operator.**
> The connector calls endpoints under **`{Server URL}{API base path}/…`**, i.e.
> `{URL}/server/protected/transaction/pdfs` with the default `/server` prefix.
> Set **Server URL** to the platform root and **do not** append `/server`
> yourself — the **API base path** setting adds it. If your instance exposes the
> API under a different context path, just change the **API base path** field
> (no code change needed).

**Network:** the Odoo server must reach the NGSign server over **outbound HTTPS
(443)**. If egress is filtered, whitelist the NGSign host.

---

## 6. Verify the install (functional smoke test)

1. **Core:** *NGSign → New Signature* → upload a small PDF → set a test signer →
   *Send for signature* (mode *By email invitation*). The signer receives the
   NGSign email, signs, and within the cron window (or via the transaction's
   **Poll status now** button) the signed PDF is retrieved and attached.
2. **Sales:** open a quotation whose customer has an email → **Envoyer pour
   signature client** → confirm the wizard → the order shows *En attente de
   signature* → after the customer signs, **Rafraîchir la signature** pulls the
   signed PDF onto the order.

---

## 7. The polling job

- Scheduled action **"NGSign: poll pending transactions"** runs every **5 minutes**
  (*Settings → Technical → Scheduled Actions*). Adjust the interval there.
- Requires cron workers enabled: `max_cron_threads >= 1` (Odoo default is 2). In
  multi-worker / multi-server setups the cron runs on one node — no extra config.
- **Webhook alternative:** NGSign supports a `callbackUrl` to be notified on
  sign/refuse instead of polling. Not enabled by default — see the roadmap in
  `TECHNICAL_MANUAL.md §10`.

---

## 8. Upgrades

1. Backup + staging first.
2. Replace the module folders with the new version (git pull / copy).
3. Upgrade:
   ```bash
   odoo -c /etc/odoo/odoo.conf -d <DB> -u ngsign,ngsign_sale --stop-after-init
   ```
   (or *Apps → NGSign → Upgrade*), then **restart** the server.

---

## 9. Uninstall

*Apps → NGSign → Uninstall*. This drops the connector models and the
`ngsign.transaction` tracking history. **Signed PDFs already attached to records
stay** (they are standard attachments). If you need the audit trail, export the
*NGSign Transactions* list first.

---

## 10. Security & operations

- **Token storage:** the API token lives in *System Parameters*
  (`ngsign.token`). Restrict Settings/Technical access to administrators;
  remember DB backups contain it. Prefer a **dedicated NGSign API user** for the
  integration (least privilege, easy revocation).
- **Errors** are logged under `odoo.addons.ngsign*` and mirrored in each
  transaction's **Last Error** field for support.
- **No special HA requirements** — the connector is stateless HTTP over the DB.

---

## 11. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Module absent from Apps | *Update Apps List*; check `addons_path`; restart the server |
| "NGSign is not configured" | Set **Server URL** + **API Token** in Settings → NGSign |
| HTTP error on *Send* | Check outbound network to NGSign, token validity, and the `/server` base path (§5) |
| Signed PDF never returns | Cron active? `max_cron_threads >= 1`? Check the transaction **Last Error**; confirm the signer actually signed |
| Quotation button missing | It shows only on `draft`/`sent` quotations; hard-refresh the browser (`Cmd/Ctrl+Shift+R`) after install |
| Sale PDF generation fails | `wkhtmltopdf` missing/misconfigured on the server |
| Changes not visible after CLI install | Restart the live Odoo server so workers reload the registry |

---

## Appendix — minimal `odoo.conf`

```ini
[options]
addons_path = /opt/odoo/custom-addons,/usr/lib/python3/dist-packages/odoo/addons
db_host = localhost
db_user = odoo
db_password = ******
max_cron_threads = 2
; workers = 4            ; if using a multi-worker deployment
; proxy_mode = True      ; if behind a reverse proxy (nginx)
```
