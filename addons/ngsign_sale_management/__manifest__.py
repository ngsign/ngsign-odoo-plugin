# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies. Licensed under LGPL-3.0 (see LICENSE).
{
    "name": "NGSign for Sales - Quotation Templates",
    "version": "17.0.1.0.0",
    "summary": "Configure the customer signature position on quotation templates",
    "description": """
NGSign - Quotation template signature position
==============================================
Adds an **Electronic signature (NGSign)** section on quotation templates
(sale.order.template) to define where the customer signature is placed. A
quotation created from a template automatically uses that position when sent for
signature, so the customer signs without placing a stamp.

Bridge module: installs automatically when both **ngsign_sale** and
**sale_management** are present. Without a template, the global NGSign position
settings apply.
""",
    "author": "NG Technologies",
    "website": "https://www.ng-sign.com",
    "license": "LGPL-3",
    "category": "Sales",
    "depends": ["ngsign_sale", "sale_management"],
    "data": [
        "views/sale_order_template_views.xml",
    ],
    "auto_install": True,
    "installable": True,
}
