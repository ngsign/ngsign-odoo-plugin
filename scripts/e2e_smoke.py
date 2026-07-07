#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies. Licensed under LGPL-3.0.
"""Standalone end-to-end smoke test of the NGSign client against the mock.

Exercises the exact contract the Odoo plugin relies on, WITHOUT needing Odoo or
a database. Run it against the mock exposed on the host:

    python3 scripts/e2e_smoke.py --url http://localhost:8090

Exit code 0 = the full upload -> launch -> sign -> poll -> download cycle works.
"""

import argparse
import base64
import os
import sys

# Import the real plugin client so we test the same code the addon runs.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addons", "ngsign", "models"))
from ngsign_client import NgsignClient, NgsignError  # noqa: E402

import requests  # noqa: E402

_PDF_B64 = (
    "JVBERi0xLjQKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFI+PgplbmRvYmoKMiAw"
    "IG9iago8PC9UeXBlL1BhZ2VzL0tpZHNbMyAwIFJdL0NvdW50IDE+PgplbmRvYmoKMyAwIG9iago8"
    "PC9UeXBlL1BhZ2UvUGFyZW50IDIgMCBSL01lZGlhQm94WzAgMCA2MTIgNzkyXT4+CmVuZG9iagp0"
    "cmFpbGVyCjw8L1Jvb3QgMSAwIFI+PgolJUVPRgo="
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8090",
                        help="NGSign mock base URL (host side)")
    parser.add_argument("--token", default="smoke-token")
    parser.add_argument("--prefix", default="/server",
                        help="API context path prefix (default /server)")
    args = parser.parse_args()

    client = NgsignClient(args.url, args.token, api_prefix=args.prefix)
    ok = True

    def check(label, cond):
        nonlocal ok
        status = "PASS" if cond else "FAIL"
        print("[%s] %s" % (status, label))
        ok = ok and cond

    try:
        # 1. Upload
        upload = client.upload_pdf("contract.pdf", _PDF_B64)
        tx_id, doc_id = NgsignClient.extract_upload_ids(upload)
        check("upload returns transaction + document ids", bool(tx_id and doc_id))
        check("status after upload is CREATED",
              NgsignClient.extract_status(upload) == "CREATED")

        # 2. Launch
        sig_conf = [{
            "signer": {"firstName": "Alice", "lastName": "Signer",
                       "email": "alice@example.com", "phoneNumber": ""},
            "sigType": "CERTIFIED_TIMESTAMP",
            "choosePosition": True,
            "docsConfigs": [{"documentName": "contract", "documentExtension": "pdf",
                             "identifier": doc_id}],
            "mode": "BY_MAIL",
            "otp": "NONE",
        }]
        launched = client.launch(tx_id, sig_conf)
        check("launch moves status to SIGNATURE_LAUNCHED",
              NgsignClient.extract_status(launched) == "SIGNATURE_LAUNCHED")

        # 3. Poll before signing -> not yet signed
        info = client.get_transaction(tx_id)
        check("still pending before signing",
              NgsignClient.extract_status(info) not in
              ("SIGNED", "COMPLETED", "FINISHED", "VALIDATED", "DONE"))

        # 4. Simulate signing via the mock helper
        resp = requests.post("%s/_mock/sign/%s" % (args.url.rstrip("/"), tx_id),
                             headers={"Authorization": "Bearer " + args.token}, timeout=30)
        check("mock accepts simulated signature", resp.status_code < 300)

        # 5. Poll again -> SIGNED
        info = client.get_transaction(tx_id)
        check("status becomes SIGNED after signing",
              NgsignClient.extract_status(info) == "SIGNED")

        # 6. Download signed PDF
        pdf = client.download_pdf(tx_id, doc_id)
        check("signed PDF downloads and starts with %PDF", pdf.startswith(b"%PDF"))

    except (NgsignError, requests.RequestException) as exc:
        print("[FAIL] unexpected error: %s" % exc)
        ok = False

    print("\n%s" % ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
