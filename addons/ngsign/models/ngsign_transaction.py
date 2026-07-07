# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies. Licensed under LGPL-3.0 (see LICENSE).
"""Local tracking of NGSign signature transactions.

Mirrors the ``ngsign_transactions`` table used by the Maarch connector, plus the
poll/retrieve logic of ``NgsignController::retrieveSignedMails``.
"""

import base64
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .ngsign_client import NgsignClient, NgsignError

_logger = logging.getLogger(__name__)

# Same tolerant state sets as the Maarch connector.
SIGNED_STATES = {"SIGNED", "COMPLETED", "FINISHED", "VALIDATED", "DONE"}
CLOSED_STATES = {"REJECTED", "REFUSED", "CANCELLED", "CANCELED", "EXPIRED"}


class NgsignTransaction(models.Model):
    _name = "ngsign.transaction"
    _description = "NGSign Signature Transaction"
    _inherit = ["mail.thread"]
    _order = "create_date desc"
    _rec_name = "name"

    name = fields.Char("Transaction UUID", required=True, index=True, readonly=True)
    document_identifier = fields.Char("Document Identifier", required=True, readonly=True)
    status = fields.Selection(
        [
            ("SENT", "Sent"),
            ("LAUNCHED", "Launched"),
            ("SIGNED", "Signed"),
            ("REJECTED", "Rejected"),
            ("CANCELLED", "Cancelled"),
            ("EXPIRED", "Expired"),
            ("ERROR", "Error"),
        ],
        default="SENT", required=True, index=True, tracking=True,
    )

    # Link back to the Odoo record the document belongs to (optional).
    res_model = fields.Char("Source Model", readonly=True)
    res_id = fields.Integer("Source Record ID", readonly=True)
    source_attachment_id = fields.Many2one(
        "ir.attachment", "Source PDF", readonly=True, ondelete="set null")
    signed_attachment_id = fields.Many2one(
        "ir.attachment", "Signed PDF", readonly=True, ondelete="set null")

    signer_firstname = fields.Char("Signer First Name", readonly=True)
    signer_lastname = fields.Char("Signer Last Name", readonly=True)
    signer_email = fields.Char("Signer Email", readonly=True)
    signer_phone = fields.Char("Signer Phone", readonly=True)
    sig_type = fields.Char("Signature Type", readonly=True)
    mode = fields.Char("Signature Mode", readonly=True)
    next_signer = fields.Char("Next Signer UUID", readonly=True)
    signing_url = fields.Char("Signing URL", compute="_compute_signing_url")
    last_error = fields.Text("Last Error", readonly=True)

    # -- Configuration ------------------------------------------------------

    def _get_config(self):
        icp = self.env["ir.config_parameter"].sudo()
        base_url = icp.get_param("ngsign.base_url")
        token = icp.get_param("ngsign.token")
        if not base_url or not token:
            raise UserError(_(
                "NGSign is not configured. Set the server URL and API token in "
                "Settings > NGSign."))
        return base_url, token

    def _get_client(self):
        base_url, token = self._get_config()
        # get_param returns the fallback when the key is absent (not None/False).
        api_prefix = self.env["ir.config_parameter"].sudo().get_param(
            "ngsign.api_base_path", "/server")
        return NgsignClient(base_url, token, api_prefix=api_prefix)

    @api.depends("name", "next_signer")
    def _compute_signing_url(self):
        icp = self.env["ir.config_parameter"].sudo()
        base_url = icp.get_param("ngsign.base_url") or ""
        core = icp.get_param("ngsign.api_base_path", "/server").strip().strip("/")
        prefix = ("/" + core) if core else ""
        server = base_url.rstrip("/")
        # The PDS (signing page) lives at the web root, not under the API prefix.
        if prefix and server.endswith(prefix):
            server = server[: -len(prefix)].rstrip("/")
        for tx in self:
            if tx.name and tx.next_signer:
                tx.signing_url = "%s/pds/#/transaction/sign/%s?uuid=%s" % (
                    server, tx.next_signer, tx.name)
            else:
                tx.signing_url = False

    # -- Polling / retrieval ------------------------------------------------

    def action_poll(self):
        for tx in self:
            tx._poll_one()
        return True

    def _poll_one(self):
        self.ensure_one()
        if self.status in ("SIGNED", "REJECTED", "CANCELLED", "EXPIRED"):
            return
        client = self._get_client()
        try:
            info = client.get_transaction(self.name)
            status = NgsignClient.extract_status(info)
            if status in SIGNED_STATES:
                pdf_bytes = client.download_pdf(self.name, self.document_identifier)
                self._attach_signed_pdf(pdf_bytes)
                self.write({"status": "SIGNED", "last_error": False})
                self._post_source_message(
                    _("Document signed via NGSign (transaction %s).") % self.name)
            elif status in CLOSED_STATES:
                new_status = "EXPIRED" if status == "EXPIRED" else (
                    "CANCELLED" if "CANCEL" in status else "REJECTED")
                self.write({"status": new_status, "last_error": False})
                self._post_source_message(
                    _("Signature %s via NGSign (%s).") % (new_status.lower(), status))
            elif self.status == "SENT":
                self.write({"status": "LAUNCHED"})
        except NgsignError as exc:
            self.write({"last_error": str(exc)})
            _logger.warning("NGSign poll error for %s: %s", self.name, exc)

    def _attach_signed_pdf(self, pdf_bytes):
        self.ensure_one()
        base_name = self.source_attachment_id.name or self.name or "document"
        if not base_name.lower().endswith(".pdf"):
            base_name += ".pdf"
        vals = {
            "name": "SIGNED_" + base_name,
            "datas": base64.b64encode(pdf_bytes),
            "mimetype": "application/pdf",
        }
        if self.res_model and self.res_id:
            vals["res_model"] = self.res_model
            vals["res_id"] = self.res_id
        att = self.env["ir.attachment"].create(vals)
        self.signed_attachment_id = att.id

    def _post_source_message(self, body):
        self.ensure_one()
        if not (self.res_model and self.res_id):
            return
        if self.res_model not in self.env:
            return
        record = self.env[self.res_model].browse(self.res_id)
        if record.exists() and hasattr(record, "message_post"):
            record.message_post(
                body=body,
                attachment_ids=self.signed_attachment_id.ids or [])

    # -- Cancel -------------------------------------------------------------

    def action_cancel(self):
        for tx in self:
            if tx.status in ("SIGNED", "CANCELLED"):
                continue
            client = tx._get_client()
            try:
                client.cancel(tx.name)
                tx.write({"status": "CANCELLED", "last_error": False})
            except NgsignError as exc:
                raise UserError(
                    _("Unable to cancel transaction %s: %s") % (tx.name, exc))
        return True

    # -- Dev helper: simulate a signature on the local mock -----------------

    def action_simulate_mock_sign(self):
        """POST {base_url}/_mock/sign/{uuid} — only works against the POC mock."""
        self.ensure_one()
        base_url, token = self._get_config()
        url = base_url.rstrip("/") + "/_mock/sign/" + self.name
        try:
            resp = requests.post(
                url, headers={"Authorization": "Bearer " + token}, timeout=30)
        except requests.RequestException as exc:
            raise UserError(_("Mock not reachable at %s: %s") % (url, exc))
        if resp.status_code >= 300:
            raise UserError(_(
                "Mock did not accept the simulated signature (HTTP %s). This "
                "action only works against the POC mock server.") % resp.status_code)
        return self.action_poll()

    # -- Cron ---------------------------------------------------------------

    @api.model
    def _cron_poll_pending(self):
        pending = self.search([("status", "in", ("SENT", "LAUNCHED"))])
        _logger.info("NGSign cron: polling %s pending transaction(s)", len(pending))
        for tx in pending:
            tx._poll_one()
        return True
