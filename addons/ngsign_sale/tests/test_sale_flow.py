# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies. Licensed under LGPL-3.0.
"""E2E test of the quotation signature flow against the NGSign mock.

Opt-in via NGSIGN_TEST_URL (same as the base module test). '-standard' is
required so Odoo's test harness does not block the real HTTP call to the mock.
"""

import os
import unittest

from odoo.tests import TransactionCase, tagged

_MOCK_URL = os.environ.get("NGSIGN_TEST_URL")


@tagged("post_install", "-at_install", "-standard", "ngsign")
@unittest.skipUnless(_MOCK_URL, "Set NGSIGN_TEST_URL to run the NGSign mock integration test")
class TestSaleSignatureFlow(TransactionCase):

    def setUp(self):
        super().setUp()
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("ngsign.base_url", _MOCK_URL)
        icp.set_param("ngsign.token", "test-token")

        self.partner = self.env["res.partner"].create({
            "name": "Alice Buyer",
            "email": "alice.buyer@example.com",
            "phone": "+21600000000",
        })
        product = self.env["product.product"].create({
            "name": "Consulting", "type": "service", "list_price": 100.0,
        })
        self.order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": 2})],
        })

    def test_quotation_signature_cycle(self):
        # 1. "Envoyer pour signature client" -> opens the prefilled wizard.
        action = self.order.action_ngsign_send_for_signature()
        self.assertEqual(action["res_model"], "ngsign.send.wizard")
        ctx = action["context"]
        self.assertEqual(ctx["default_res_model"], "sale.order")
        self.assertEqual(ctx["default_signer_email"], "alice.buyer@example.com")
        self.assertTrue(ctx["default_pdf_file"], "Quotation PDF should be generated")

        # 2. Confirm the wizard (as the user clicking "Send").
        wizard = self.env["ngsign.send.wizard"].with_context(**ctx).create({})
        wizard.action_send()

        # 3. The order now shows a waiting signature status.
        self.order.invalidate_recordset(["ngsign_transaction_id", "ngsign_status"])
        tx = self.order.ngsign_transaction_id
        self.assertTrue(tx, "The order should be linked to an NGSign transaction")
        self.assertIn(self.order.ngsign_status, ("SENT", "LAUNCHED"))

        # 4. Customer signs (simulated on the mock) + "Rafraîchir".
        tx.action_simulate_mock_sign()
        self.order.invalidate_recordset(["ngsign_status"])
        self.assertEqual(self.order.ngsign_status, "SIGNED")

        # 5. The signed PDF is attached back to the order.
        signed = self.env["ir.attachment"].search([
            ("res_model", "=", "sale.order"),
            ("res_id", "=", self.order.id),
            ("name", "=like", "SIGNED_%"),
        ])
        self.assertTrue(signed, "Signed PDF should be attached to the sale order")
