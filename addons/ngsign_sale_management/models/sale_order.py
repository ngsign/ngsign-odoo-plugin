# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies. Licensed under LGPL-3.0 (see LICENSE).
"""Feed the quotation template's signature position into the send wizard."""

from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _ngsign_extra_context(self):
        ctx = super()._ngsign_extra_context()
        template = self.sale_order_template_id
        if template:
            ctx.update({
                "default_choose_position": template.ngsign_choose_position,
                "default_page": template.ngsign_sig_page or 1,
                "default_x_axis": template.ngsign_sig_x or 0,
                "default_y_axis": template.ngsign_sig_y or 0,
            })
        return ctx
