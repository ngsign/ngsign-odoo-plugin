# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies. Licensed under LGPL-3.0.
"""End-to-end integration test of the Odoo plugin against the NGSign mock.

Opt-in: set NGSIGN_TEST_URL to the mock base URL (e.g. http://ngsign-mock:8080
from inside the compose network) before running:

    docker compose exec -e NGSIGN_TEST_URL=http://ngsign-mock:8080 \\
        odoo odoo -d odoo -i ngsign --test-enable --test-tags /ngsign --stop-after-init

Without that variable the test is skipped (no external dependency in plain CI).
"""

import base64
import os
import unittest

from odoo.tests import TransactionCase, tagged

# A tiny but structurally valid one-page PDF.
_PDF_B64 = (
    "JVBERi0xLjQKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFI+PgplbmRvYmoKMiAw"
    "IG9iago8PC9UeXBlL1BhZ2VzL0tpZHNbMyAwIFJdL0NvdW50IDE+PgplbmRvYmoKMyAwIG9iago8"
    "PC9UeXBlL1BhZ2UvUGFyZW50IDIgMCBSL01lZGlhQm94WzAgMCA2MTIgNzkyXT4+CmVuZG9iagp0"
    "cmFpbGVyCjw8L1Jvb3QgMSAwIFI+PgolJUVPRgo="
)

_MOCK_URL = os.environ.get("NGSIGN_TEST_URL")


# '-standard' is required: Odoo's standard test harness patches
# requests.Session.send and blocks every non-localhost HTTP call
# ("External requests verboten"). Dropping the 'standard' tag disables that
# patch so this opt-in test can reach the local NGSign mock for real.
@tagged("post_install", "-at_install", "-standard", "ngsign")
@unittest.skipUnless(_MOCK_URL, "Set NGSIGN_TEST_URL to run the NGSign mock integration test")
class TestNgsignFlow(TransactionCase):

    def setUp(self):
        super().setUp()
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("ngsign.base_url", _MOCK_URL)
        icp.set_param("ngsign.token", "test-token")

    def test_full_signature_cycle(self):
        # 1. Send a PDF through the wizard (BY_MAIL).
        wizard = self.env["ngsign.send.wizard"].create({
            "pdf_file": _PDF_B64,
            "pdf_filename": "contract.pdf",
            "signer_firstname": "Alice",
            "signer_lastname": "Signer",
            "signer_email": "alice@example.com",
            "sig_type": "CERTIFIED_TIMESTAMP",
            "mode": "BY_MAIL",
            "otp": "NONE",
        })
        action = wizard.action_send()
        tx = self.env["ngsign.transaction"].browse(action["res_id"])
        self.assertTrue(tx.name, "Transaction UUID should be set")
        self.assertTrue(tx.document_identifier, "Document identifier should be set")
        self.assertEqual(tx.status, "SENT")

        # Position is pre-configured by default (choose_position off): the
        # connector must send choosePosition=false + a page/x/y so the signer
        # does not have to place the stamp.
        sent = tx._get_client().get_transaction(tx.name)["object"]["signers"][0]
        self.assertFalse(sent["choosePosition"])
        doc_cfg = sent["docsConfigs"][0]
        self.assertEqual(doc_cfg["page"], 1)
        self.assertIn("xAxis", doc_cfg)
        self.assertIn("yAxis", doc_cfg)

        # 2. Polling before signing -> still pending (LAUNCHED).
        tx.action_poll()
        self.assertIn(tx.status, ("SENT", "LAUNCHED"))
        self.assertFalse(tx.signed_attachment_id)

        # 3. Simulate the signer signing on the mock, then poll.
        tx.action_simulate_mock_sign()
        self.assertEqual(tx.status, "SIGNED")

        # 4. The signed PDF is retrieved and attached.
        self.assertTrue(tx.signed_attachment_id, "Signed PDF should be attached")
        signed = base64.b64decode(tx.signed_attachment_id.datas)
        self.assertTrue(signed.startswith(b"%PDF"), "Signed attachment should be a PDF")
