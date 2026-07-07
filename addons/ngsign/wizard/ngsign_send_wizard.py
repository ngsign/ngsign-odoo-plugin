# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies. Licensed under LGPL-3.0 (see LICENSE).
"""Wizard: push a PDF to NGSign and launch a signature transaction."""

import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.ngsign_client import NgsignClient, NgsignError

SIG_TYPES = [
    ("LATER", "Choose later (on the signing page)"),
    ("CERTIFIED_TIMESTAMP", "Simple signature (timestamp)"),
    ("SIGNATURE_WITH_SSCD", "Qualified - SSCD token"),
    ("REMOTE_SIGN", "Qualified - Remote Trust"),
    ("DIGI_GO", "DigiGO (TunTrust)"),
    ("MOBILE_ID", "MobileID / E-Houwiya"),
]
MODES = [
    ("BY_MAIL", "By email invitation"),
    ("BY_LINK", "By link"),
    ("FACE_TO_FACE", "Face to face"),
]
OTP_MODES = [
    ("NONE", "No OTP"),
    ("OTP", "OTP by SMS"),
    ("EMAIL", "OTP by email"),
]


class NgsignSendWizard(models.TransientModel):
    _name = "ngsign.send.wizard"
    _description = "Send a document to NGSign for signature"

    # Source document: an existing PDF attachment, OR a freshly uploaded file.
    attachment_id = fields.Many2one(
        "ir.attachment", string="Existing PDF attachment",
        domain="[('mimetype', '=', 'application/pdf')]")
    pdf_file = fields.Binary("Or upload a PDF")
    pdf_filename = fields.Char("File name")

    res_model = fields.Char()
    res_id = fields.Integer()

    signer_firstname = fields.Char("First name", required=True)
    signer_lastname = fields.Char("Last name", required=True)
    signer_email = fields.Char("Email", required=True)
    signer_phone = fields.Char("Phone")

    sig_type = fields.Selection(SIG_TYPES, string="Signature type",
                                required=True, default="CERTIFIED_TIMESTAMP")
    mode = fields.Selection(MODES, string="Signature mode",
                            required=True, default="BY_MAIL")
    otp = fields.Selection(OTP_MODES, string="OTP", required=True, default="NONE")

    choose_position = fields.Boolean(
        "Signer chooses signature position", default=True,
        help="If enabled, the signer places the visible signature on the NGSign "
             "signing page. Disable to send a fixed page/x/y position.")
    page = fields.Integer("Page", default=1)
    x_axis = fields.Integer("X position", default=81)
    y_axis = fields.Integer("Y position", default=44)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        # Launched from the "Send to NGSign" action on an attachment.
        if ctx.get("active_model") == "ir.attachment" and ctx.get("active_id"):
            att = self.env["ir.attachment"].browse(ctx["active_id"])
            if att.exists():
                res["attachment_id"] = att.id
                if att.res_model and att.res_id:
                    res["res_model"] = att.res_model
                    res["res_id"] = att.res_id
        icp = self.env["ir.config_parameter"].sudo()
        # Settings-driven defaults; an explicit context default_* always wins.
        if "default_sig_type" not in ctx:
            res["sig_type"] = icp.get_param("ngsign.default_sig_type") or "CERTIFIED_TIMESTAMP"
        if "default_mode" not in ctx:
            res["mode"] = icp.get_param("ngsign.default_mode") or "BY_MAIL"
        if "default_choose_position" not in ctx:
            res["choose_position"] = self._cfg_bool(icp, "ngsign.choose_position", False)
        if "default_page" not in ctx:
            res["page"] = self._cfg_int(icp, "ngsign.default_page", 1)
        if "default_x_axis" not in ctx:
            res["x_axis"] = self._cfg_int(icp, "ngsign.default_x", 81)
        if "default_y_axis" not in ctx:
            res["y_axis"] = self._cfg_int(icp, "ngsign.default_y", 45)
        return res

    @staticmethod
    def _cfg_bool(icp, key, default):
        val = icp.get_param(key)
        if val in (False, None, ""):
            return default
        return str(val).strip().lower() in ("1", "true", "yes", "on")

    @staticmethod
    def _cfg_int(icp, key, default):
        try:
            return int(icp.get_param(key))
        except (TypeError, ValueError):
            return default

    # -- Helpers ------------------------------------------------------------

    def _resolve_source(self):
        """Return (file_name, base64_str, source_attachment)."""
        self.ensure_one()
        if self.attachment_id:
            att = self.attachment_id
            if att.mimetype != "application/pdf":
                raise UserError(_("The selected attachment is not a PDF."))
            return att.name, self._as_str(att.datas), att
        if self.pdf_file:
            name = self.pdf_filename or "document.pdf"
            att = self.env["ir.attachment"].create({
                "name": name,
                "datas": self.pdf_file,
                "mimetype": "application/pdf",
                "res_model": self.res_model or False,
                "res_id": self.res_id or 0,
            })
            return name, self._as_str(self.pdf_file), att
        raise UserError(_("Please select a PDF attachment or upload a file."))

    @staticmethod
    def _as_str(value):
        return value.decode() if isinstance(value, bytes) else value

    @staticmethod
    def _safe_name(title):
        name = re.sub(r"[^A-Za-z0-9_\- ]", "", title or "").strip() or "document"
        return name[:120]

    # -- Action -------------------------------------------------------------

    def action_send(self):
        self.ensure_one()
        # Single source of truth for base URL / token / API prefix.
        client = self.env["ngsign.transaction"]._get_client()

        file_name, base64_pdf, source_att = self._resolve_source()
        safe_name = self._safe_name(file_name)

        try:
            upload = client.upload_pdf(safe_name, base64_pdf)
            transaction_id, identifier = NgsignClient.extract_upload_ids(upload)

            doc_config = {
                "documentName": safe_name,
                "documentExtension": "pdf",
                "identifier": identifier,
            }
            if not self.choose_position:
                doc_config["page"] = self.page or 1
                doc_config["xAxis"] = self.x_axis or 0
                doc_config["yAxis"] = self.y_axis or 0

            sig_conf = [{
                "signer": {
                    "firstName": self.signer_firstname,
                    "lastName": self.signer_lastname,
                    "email": self.signer_email,
                    "phoneNumber": self.signer_phone or "",
                },
                "sigType": self.sig_type,
                "choosePosition": self.choose_position,
                "docsConfigs": [doc_config],
                "mode": self.mode,
                "otp": self.otp,
            }]

            launched = client.launch(transaction_id, sig_conf)
            next_signer = NgsignClient.extract_next_signer(launched)
        except NgsignError as exc:
            raise UserError(_("NGSign error: %s") % exc)

        tx = self.env["ngsign.transaction"].create({
            "name": transaction_id,
            "document_identifier": identifier,
            "status": "SENT" if self.mode == "BY_MAIL" else "LAUNCHED",
            "res_model": self.res_model or source_att.res_model or False,
            "res_id": self.res_id or source_att.res_id or False,
            "source_attachment_id": source_att.id,
            "signer_firstname": self.signer_firstname,
            "signer_lastname": self.signer_lastname,
            "signer_email": self.signer_email,
            "signer_phone": self.signer_phone,
            "sig_type": self.sig_type,
            "mode": self.mode,
            "next_signer": next_signer,
        })

        return {
            "type": "ir.actions.act_window",
            "name": _("NGSign Transaction"),
            "res_model": "ngsign.transaction",
            "res_id": tx.id,
            "view_mode": "form",
            "target": "current",
        }
