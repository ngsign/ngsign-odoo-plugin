# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies. Licensed under LGPL-3.0 (see LICENSE).
"""Signature position configured on the quotation template."""

from odoo import fields, models


class SaleOrderTemplate(models.Model):
    _inherit = "sale.order.template"

    ngsign_choose_position = fields.Boolean(
        string="Signer places the signature",
        default=False,
        help="If enabled, the customer places the visible signature on the NGSign "
             "page. Disabled (default): the position below is applied "
             "automatically, so the customer just signs.")
    ngsign_sig_page = fields.Integer(
        string="Signature page", default=1,
        help="Page where the visible signature is placed (1 = first page).")
    ngsign_sig_x = fields.Integer(
        string="Signature X", default=81,
        help="Horizontal position of the visible signature.")
    ngsign_sig_y = fields.Integer(
        string="Signature Y", default=45,
        help="Vertical position of the visible signature.")
