# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies. Licensed under LGPL-3.0 (see LICENSE).
"""Sale order integration: send a quotation to NGSign for customer signature."""

import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Quotation / Order PDF report shipped by the sale module.
_SALE_REPORT = "sale.action_report_saleorder"

# NGSign statuses that mean "waiting for the customer to sign".
_WAITING = ("SENT", "LAUNCHED")


class SaleOrder(models.Model):
    _inherit = "sale.order"

    ngsign_transaction_id = fields.Many2one(
        "ngsign.transaction", string="NGSign transaction",
        compute="_compute_ngsign_state")
    # Selection mirrors ngsign.transaction.status. Computed alongside the
    # transaction (not related=) so Odoo does not require the non-stored
    # transaction field to be searchable.
    ngsign_status = fields.Selection(
        selection=[
            ("SENT", "Sent"),
            ("LAUNCHED", "Launched"),
            ("SIGNED", "Signed"),
            ("REJECTED", "Rejected"),
            ("CANCELLED", "Cancelled"),
            ("EXPIRED", "Expired"),
            ("ERROR", "Error"),
        ],
        string="Signature status", compute="_compute_ngsign_state")

    # No @api.depends: the "latest transaction for this order" cannot be
    # expressed as a field path. The field is non-stored and recomputed on each
    # read (and on the explicit reload after the Refresh button), which keeps
    # the status fresh without a stored dependency.
    def _compute_ngsign_state(self):
        Tx = self.env["ngsign.transaction"]
        for order in self:
            tx = Tx.search(
                [("res_model", "=", "sale.order"), ("res_id", "=", order.id)],
                order="create_date desc", limit=1)
            order.ngsign_transaction_id = tx
            order.ngsign_status = tx.status if tx else False

    # -- Actions ------------------------------------------------------------

    def action_ngsign_send_for_signature(self):
        """Generate the quotation PDF and open the NGSign wizard, prefilled with
        the customer as signer. On send, the order shows a waiting status."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("The quotation has no customer to sign it."))

        pdf_content, _ext = self.env["ir.actions.report"]._render_qweb_pdf(
            _SALE_REPORT, res_ids=self.ids)
        filename = "%s.pdf" % (self.name or "Quotation").replace("/", "_")

        first, last = self._ngsign_signer_name(self.partner_id)
        ctx = dict(
            self.env.context,
            default_pdf_file=base64.b64encode(pdf_content),
            default_pdf_filename=filename,
            default_res_model="sale.order",
            default_res_id=self.id,
            default_signer_firstname=first,
            default_signer_lastname=last,
            default_signer_email=self.partner_id.email or "",
            default_signer_phone=self.partner_id.phone or self.partner_id.mobile or "",
        )
        # Extension point: other modules (e.g. ngsign_sale_management) inject
        # extra wizard defaults here, such as a template-defined signature
        # position. Falls back to the global NGSign settings when empty.
        ctx.update(self._ngsign_extra_context())
        return {
            "type": "ir.actions.act_window",
            "name": _("Send for customer signature"),
            "res_model": "ngsign.send.wizard",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }

    def _ngsign_extra_context(self):
        """Hook for add-ons to inject extra defaults into the send wizard
        (e.g. a signature position defined on the quotation template).
        Return a dict of ``default_*`` context keys. Empty by default."""
        self.ensure_one()
        return {}

    def action_ngsign_refresh(self):
        """Poll NGSign for the current transaction and pull the signed PDF."""
        self.ensure_one()
        if not self.ngsign_transaction_id:
            raise UserError(_("No signature request is pending for this order."))
        self.ngsign_transaction_id.action_poll()
        return True

    def action_ngsign_open_transaction(self):
        self.ensure_one()
        if not self.ngsign_transaction_id:
            raise UserError(_("No signature request for this order."))
        return {
            "type": "ir.actions.act_window",
            "name": _("NGSign Transaction"),
            "res_model": "ngsign.transaction",
            "res_id": self.ngsign_transaction_id.id,
            "view_mode": "form",
            "target": "current",
        }

    # -- Helpers ------------------------------------------------------------

    @staticmethod
    def _ngsign_signer_name(partner):
        """Best-effort split of a partner name into (first, last), both non-empty
        (NGSign requires a first and last name)."""
        name = (partner.name or "Client").strip()
        parts = name.split(" ", 1)
        first = parts[0]
        last = parts[1].strip() if len(parts) > 1 and parts[1].strip() else first
        return first, last
