# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies. Licensed under LGPL-3.0.
"""The quotation template's signature position flows through to NGSign.

Opt-in via NGSIGN_TEST_URL; '-standard' so Odoo does not block the real HTTP
call to the mock.
"""

import os
import unittest

from odoo.tests import TransactionCase, tagged

_MOCK_URL = os.environ.get("NGSIGN_TEST_URL")


@tagged("post_install", "-at_install", "-standard", "ngsign")
@unittest.skipUnless(_MOCK_URL, "Set NGSIGN_TEST_URL to run the NGSign mock integration test")
class TestTemplatePosition(TransactionCase):

    def setUp(self):
        super().setUp()
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("ngsign.base_url", _MOCK_URL)
        icp.set_param("ngsign.token", "test-token")

        partner = self.env["res.partner"].create({
            "name": "Bob Buyer", "email": "bob.buyer@example.com",
        })
        product = self.env["product.product"].create({
            "name": "License", "type": "service", "list_price": 50.0,
        })
        # Template with a NON-default signature position.
        self.template = self.env["sale.order.template"].create({
            "name": "Signed contract template",
            "ngsign_choose_position": False,
            "ngsign_sig_page": 2,
            "ngsign_sig_x": 123,
            "ngsign_sig_y": 456,
        })
        self.order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "sale_order_template_id": self.template.id,
            "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": 1})],
        })

    def test_template_position_flows_to_ngsign(self):
        # 1. The send action carries the template position in its context.
        action = self.order.action_ngsign_send_for_signature()
        ctx = action["context"]
        self.assertFalse(ctx["default_choose_position"])
        self.assertEqual(ctx["default_page"], 2)
        self.assertEqual(ctx["default_x_axis"], 123)
        self.assertEqual(ctx["default_y_axis"], 456)

        # 2. And it is actually sent to NGSign in the sigConf.
        wizard = self.env["ngsign.send.wizard"].with_context(**ctx).create({})
        wizard.action_send()
        self.order.invalidate_recordset(["ngsign_transaction_id"])
        tx = self.order.ngsign_transaction_id
        self.assertTrue(tx)
        signer = tx._get_client().get_transaction(tx.name)["object"]["signers"][0]
        self.assertFalse(signer["choosePosition"])
        doc = signer["docsConfigs"][0]
        self.assertEqual(doc["page"], 2)
        self.assertEqual(doc["xAxis"], 123)
        self.assertEqual(doc["yAxis"], 456)
