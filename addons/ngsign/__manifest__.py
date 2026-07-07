# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies. Licensed under LGPL-3.0 (see LICENSE).
{
    "name": "NGSign Electronic Signature",
    "version": "17.0.1.0.0",
    "summary": "Send Odoo PDF documents to NGSign for electronic signature",
    "description": """
NGSign connector for Odoo
=========================
Push any PDF attachment (invoice, quotation, contract...) to the NGSign
electronic signature platform, then automatically retrieve the signed PDF and
re-attach it to the source record.

Full cycle: select a PDF -> upload + launch on NGSign -> the signer signs
(email invitation, link or face to face) -> a scheduled job polls NGSign and
re-integrates the signed document into Odoo.
""",
    "author": "NG Technologies",
    "website": "https://www.ng-sign.com",
    "license": "LGPL-3",
    "category": "Document Management",
    "depends": ["base", "mail"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/res_config_settings_views.xml",
        "views/ngsign_transaction_views.xml",
        "views/ngsign_send_wizard_views.xml",
        "views/ngsign_menus.xml",
    ],
    "application": True,
    "installable": True,
}
