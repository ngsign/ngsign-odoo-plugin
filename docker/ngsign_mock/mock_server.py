#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies. Licensed under LGPL-3.0.
"""Minimal in-memory mock of the NGSign REST API for local POC validation.

Implements only the endpoints the Odoo plugin uses, faithful to the real API's
``{object, errorCode, message}`` envelope. NOT for production: no persistence,
no real signing, auth only checks that a Bearer header is present.

Real endpoints:
    POST /server/protected/transaction/pdfs
    POST /server/protected/transaction/{uuid}/launch
    POST /server/protected/transaction/{uuid}/cancel
    GET  /server/any/transaction/{uuid}
    GET  /server/any/transaction/{uuid}/pdfs/{identifier}
    GET  /server/protected/user/verify           -> 204

Test helpers (not in the real API):
    POST /_mock/sign/{uuid}      -> mark transaction SIGNED
    POST /_mock/reject/{uuid}    -> mark transaction REJECTED
    GET  /_mock/state            -> dump in-memory state
    GET  /                       -> health check

Pure standard library, no external dependency. Run: python mock_server.py
Listens on 0.0.0.0:8080 (override with the PORT env var).
"""

import base64
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_LOCK = threading.Lock()
_TX = {}          # transaction uuid -> transaction dict
_SEQ = {"n": 0}   # deterministic id counter (no randomness needed for a mock)

# API context path, mirrors the connector's configurable prefix (default /server).
_p = os.environ.get("API_PREFIX", "/server").strip().strip("/")
PREFIX = ("/" + _p) if _p else ""


def _next_id(prefix):
    _SEQ["n"] += 1
    return "%s-%08d" % (prefix, _SEQ["n"])


def _envelope(obj):
    return {"object": obj, "errorCode": None, "message": None}


class Handler(BaseHTTPRequestHandler):
    # ------------------------------------------------------------------ utils
    def _send(self, code, payload=None, raw=None, content_type="application/json"):
        body = b""
        if raw is not None:
            body = raw
        elif payload is not None:
            body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _error(self, code, error_code, message):
        self._send(code, {"object": None, "errorCode": error_code, "message": message})

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except ValueError:
            return None

    def _authed(self):
        auth = self.headers.get("Authorization", "")
        return auth.startswith("Bearer ") and len(auth) > len("Bearer ")

    def log_message(self, fmt, *args):  # quieter logs
        pass

    # ------------------------------------------------------------------- GET
    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/":
            return self._send(200, {"service": "ngsign-mock", "transactions": len(_TX)})
        if path == "/_mock/state":
            with _LOCK:
                dump = {k: {kk: vv for kk, vv in v.items() if kk != "pdfs"}
                        for k, v in _TX.items()}
            return self._send(200, dump)
        if path == PREFIX + "/protected/user/verify":
            return self._send(204 if self._authed() else 302)

        m = re.match(r"^%s/any/transaction/([^/]+)/pdfs/([^/]+)$" % re.escape(PREFIX), path)
        if m:
            return self._download(m.group(1), m.group(2))

        m = re.match(r"^%s/any/transaction/([^/]+)/?$" % re.escape(PREFIX), path)
        if m:
            return self._get_transaction(m.group(1))

        return self._error(404, 0, "Unknown GET route: %s" % path)

    # ------------------------------------------------------------------ POST
    def do_POST(self):
        path = self.path.split("?", 1)[0]

        m = re.match(r"^/_mock/(sign|reject)/([^/]+)$", path)
        if m:
            return self._mock_transition(m.group(2), m.group(1))

        if path == PREFIX + "/protected/transaction/pdfs":
            if not self._authed():
                return self._error(400, 0, "Missing Bearer token")
            return self._upload()

        m = re.match(r"^%s/protected/transaction/([^/]+)/launch$" % re.escape(PREFIX), path)
        if m:
            if not self._authed():
                return self._error(400, 0, "Missing Bearer token")
            return self._launch(m.group(1))

        m = re.match(r"^%s/protected/transaction/([^/]+)/cancel$" % re.escape(PREFIX), path)
        if m:
            if not self._authed():
                return self._error(400, 0, "Missing Bearer token")
            return self._cancel(m.group(1))

        return self._error(404, 0, "Unknown POST route: %s" % path)

    # -------------------------------------------------------------- handlers
    def _upload(self):
        body = self._read_json()
        if not isinstance(body, list) or not body:
            return self._error(400, 101, "Expected a non-empty list of NGFileUpload")
        tx_uuid = _next_id("tx")
        pdfs = []
        with _LOCK:
            for item in body:
                doc_id = _next_id("doc")
                b64 = item.get("fileBase64") or ""
                try:
                    size = len(base64.b64decode(b64))
                except Exception:
                    return self._error(400, 255, "Invalid PDF file encoding")
                pdfs.append({
                    "identifier": doc_id,
                    "name": item.get("fileName") or "document",
                    "extension": "pdf",
                    "size": size,
                    "_base64": b64,
                })
            _TX[tx_uuid] = {
                "uuid": tx_uuid,
                "status": "CREATED",
                "pdfs": pdfs,
                "signers": [],
                "nextSigner": None,
            }
        return self._send(200, _envelope(self._public(_TX[tx_uuid])))

    def _launch(self, tx_uuid):
        body = self._read_json() or {}
        with _LOCK:
            tx = _TX.get(tx_uuid)
            if not tx:
                return self._error(400, 102, "This transaction does not exist.")
            sig_conf = body.get("sigConf") or []
            signers = []
            next_signer = None
            for conf in sig_conf:
                signer = conf.get("signer") or {}
                signer_uuid = _next_id("signer")
                signers.append({
                    "signer": signer,
                    "status": "PENDING",
                    "type": conf.get("sigType"),
                    "mode": conf.get("mode"),
                    "uuid": signer_uuid,
                    # Echo back so tests can assert what the connector sent.
                    "choosePosition": conf.get("choosePosition"),
                    "docsConfigs": conf.get("docsConfigs"),
                })
                if next_signer is None and conf.get("mode") == "FACE_TO_FACE":
                    next_signer = signer_uuid
            # For BY_LINK we also expose a nextSigner so the caller can redirect.
            if next_signer is None and signers and sig_conf[0].get("mode") == "BY_LINK":
                next_signer = signers[0]["uuid"]
            tx["status"] = "SIGNATURE_LAUNCHED"
            tx["signers"] = signers
            tx["nextSigner"] = next_signer
        return self._send(200, _envelope(self._public(tx)))

    def _cancel(self, tx_uuid):
        with _LOCK:
            tx = _TX.get(tx_uuid)
            if not tx:
                return self._error(400, 102, "This transaction does not exist.")
            if tx["status"] == "SIGNED":
                return self._error(400, 105, "This transaction is already signed.")
            tx["status"] = "CANCELLED"
        return self._send(200, _envelope(self._public(tx)))

    def _get_transaction(self, tx_uuid):
        with _LOCK:
            tx = _TX.get(tx_uuid)
            if not tx:
                return self._error(400, 102, "This transaction does not exist.")
            payload = _envelope(self._public(tx))
        return self._send(200, payload)

    def _download(self, tx_uuid, identifier):
        with _LOCK:
            tx = _TX.get(tx_uuid)
            if not tx:
                return self._error(400, 102, "This transaction does not exist.")
            doc = next((p for p in tx["pdfs"] if p["identifier"] == identifier), None)
            if not doc:
                return self._error(400, 262, "Document not found.")
            b64 = doc["_base64"]
        try:
            raw = base64.b64decode(b64)
        except Exception:
            raw = b""
        return self._send(200, raw=raw, content_type="application/pdf")

    def _mock_transition(self, tx_uuid, kind):
        with _LOCK:
            tx = _TX.get(tx_uuid)
            if not tx:
                return self._error(404, 102, "This transaction does not exist.")
            if kind == "sign":
                tx["status"] = "SIGNED"
                for s in tx["signers"]:
                    s["status"] = "SIGNED"
            else:
                tx["status"] = "REJECTED"
        return self._send(200, {"ok": True, "uuid": tx_uuid, "status": tx["status"]})

    @staticmethod
    def _public(tx):
        """Public view of a transaction (strips the stored base64 blobs)."""
        return {
            "uuid": tx["uuid"],
            "status": tx["status"],
            "nextSigner": tx["nextSigner"],
            "signers": tx["signers"],
            "pdfs": [{k: v for k, v in p.items() if k != "_base64"} for p in tx["pdfs"]],
        }


def main():
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("ngsign-mock listening on 0.0.0.0:%d" % port, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
