# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies. Licensed under LGPL-3.0 (see LICENSE).
{
    "name": "NGSign for Sales",
    "version": "17.0.1.0.0",
    "summary": "Send quotations to NGSign for customer electronic signature",
    "description": """
NGSign - Sales bridge
=====================
Adds a "Send for customer signature" action on quotations (sale.order):
generate the quotation PDF, send it to NGSign for the customer to sign, show a
waiting status on the order, and a "Refresh" button to pull the signed document
back and attach it to the order.

Bridge module: installs automatically when both **ngsign** and **sale** are
present.
""",
    "author": "NG Technologies",
    "website": "https://www.ng-sign.com",
    "license": "LGPL-3",
    "category": "Sales",
    "depends": ["ngsign", "sale"],
    "data": [
        "views/sale_order_views.xml",
    ],
    "auto_install": True,
    "installable": True,
}
