# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies.
# Part of the NGSign connector for Odoo.
# Licensed under the GNU Lesser General Public License v3.0 (see LICENSE).
"""Thin HTTP client for the NGSign REST API.

Python transposition of the Maarch connector's ``NgsignClient.php``: same
endpoints (``/server`` prefix), same ``{object, errorCode, message}`` envelope,
same generous timeouts. The NGSign sandbox is slow: uploads can take 80s+.

This module has NO Odoo dependency on purpose, so it can be exercised
standalone (see ``scripts/e2e_smoke.py``) and unit-tested without a database.
"""

import json
import logging

import requests

_logger = logging.getLogger(__name__)


class NgsignError(Exception):
    """Raised on any transport or protocol error while talking to NGSign."""


class NgsignClient:
    def __init__(self, base_url, token, timeout=240, connect_timeout=30,
                 api_prefix="/server"):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        # (connect, read) timeouts — the sandbox can be very slow on upload.
        self.timeout = (connect_timeout, timeout)
        # API context path. Standard NGSign deployments expose the REST API
        # under "/server" (e.g. {base_url}/server/protected/...). Configurable
        # for instances that use a different prefix (or none at all).
        self.api_prefix = self._normalize_prefix(api_prefix)

    @staticmethod
    def _normalize_prefix(prefix):
        """Return a clean "/prefix" (leading slash, no trailing slash), or "" ."""
        cleaned = (prefix or "").strip().strip("/")
        return ("/" + cleaned) if cleaned else ""

    # -- Public API ---------------------------------------------------------

    def upload_pdf(self, file_name, base64_pdf):
        """POST /server/protected/transaction/pdfs -> NGTransaction (CREATED)."""
        payload = [{
            "fileName": file_name,
            "fileExtension": "pdf",
            "fileBase64": base64_pdf,
        }]
        return self._request(
            "POST", self.api_prefix + "/protected/transaction/pdfs", payload)

    def launch(self, transaction_id, sig_conf):
        """POST .../{id}/launch with {"sigConf": [...]} -> NGTransaction."""
        return self._request(
            "POST",
            self.api_prefix + "/protected/transaction/%s/launch" % transaction_id,
            {"sigConf": sig_conf},
        )

    def get_transaction(self, transaction_id):
        """GET {prefix}/any/transaction/{id} -> NGTransaction."""
        return self._request(
            "GET", self.api_prefix + "/any/transaction/%s" % transaction_id)

    def cancel(self, transaction_id):
        """POST {prefix}/protected/transaction/{id}/cancel -> NGTransaction."""
        return self._request(
            "POST",
            self.api_prefix + "/protected/transaction/%s/cancel" % transaction_id)

    def download_pdf(self, transaction_id, identifier):
        """GET {prefix}/any/transaction/{id}/pdfs/{identifier} -> raw PDF bytes."""
        return self._request_raw(
            "GET",
            self.api_prefix + "/any/transaction/%s/pdfs/%s" % (transaction_id, identifier),
        )

    # -- Response helpers (mirror NgsignController extract* methods) ---------

    @staticmethod
    def extract_upload_ids(response):
        """Return (transaction_id, document_identifier) from an upload response.

        NGSign wraps the transaction in an "object" envelope:
            {"object": {"uuid": "...", "pdfs": [{"identifier": "..."}]}}
        """
        obj = response.get("object") or response
        transaction_id = obj.get("uuid") or obj.get("id") or response.get("transactionId")
        pdfs = obj.get("pdfs") or obj.get("documents") or response.get("pdfs") or []
        identifier = pdfs[0].get("identifier") if pdfs else None
        if not transaction_id or not identifier:
            raise NgsignError(
                "Unable to extract transactionId/identifier from NGSign upload "
                "response: %s" % json.dumps(response)[:500])
        return str(transaction_id), str(identifier)

    @staticmethod
    def extract_status(response):
        obj = response.get("object") or response
        return (obj.get("status") or response.get("status") or "").upper()

    @staticmethod
    def extract_next_signer(response):
        obj = response.get("object") or response
        return obj.get("nextSigner")

    # -- Internals ----------------------------------------------------------

    def _request(self, method, path, payload=None):
        raw = self._request_raw(method, path, payload)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            snippet = raw[:300].decode("utf-8", "replace") if isinstance(raw, bytes) else raw[:300]
            raise NgsignError("NGSign returned a non-JSON response: %s" % snippet)

    def _request_raw(self, method, path, payload=None):
        url = self.base_url + path
        headers = {"Authorization": "Bearer " + self.token}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload)
        _logger.debug("NGSign %s %s", method, url)
        try:
            resp = requests.request(
                method, url, headers=headers, data=data, timeout=self.timeout)
        except requests.RequestException as exc:
            raise NgsignError("NGSign connection error on %s: %s" % (path, exc))
        if resp.status_code < 200 or resp.status_code >= 300:
            raise NgsignError("NGSign HTTP %s on %s: %s"
                              % (resp.status_code, path, resp.text[:500]))
        return resp.content
