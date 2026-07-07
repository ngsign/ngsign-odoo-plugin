# -*- coding: utf-8 -*-
# Copyright (C) 2026 NG Technologies. Licensed under LGPL-3.0 (see LICENSE).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ngsign_base_url = fields.Char(
        string="NGSign Server URL",
        config_parameter="ngsign.base_url",
        help="Base URL of the NGSign platform (without the /server suffix), "
             "e.g. https://sandbox.ng-sign.com or, for the local POC, "
             "http://ngsign-mock:8080")
    ngsign_token = fields.Char(
        string="NGSign API Token",
        config_parameter="ngsign.token",
        help="Bearer token generated from the NGSign web application.")
    ngsign_api_base_path = fields.Char(
        string="API base path",
        config_parameter="ngsign.api_base_path",
        default="/server",
        help="Context path under which the NGSign REST API is exposed. Standard "
             "deployments use '/server' (the connector then calls "
             "{Server URL}/server/protected/...). Change it only if your NGSign "
             "instance uses a different prefix; leave empty for none.")
    ngsign_default_sig_type = fields.Selection(
        selection=[
            ("LATER", "Choose later (on the signing page)"),
            ("CERTIFIED_TIMESTAMP", "Simple signature (timestamp)"),
            ("SIGNATURE_WITH_SSCD", "Qualified - SSCD token"),
            ("REMOTE_SIGN", "Qualified - Remote Trust"),
            ("DIGI_GO", "DigiGO (TunTrust)"),
            ("MOBILE_ID", "MobileID / E-Houwiya"),
        ],
        string="Default Signature Type",
        config_parameter="ngsign.default_sig_type",
        default="CERTIFIED_TIMESTAMP")
    ngsign_default_mode = fields.Selection(
        selection=[
            ("BY_MAIL", "By email invitation"),
            ("BY_LINK", "By link (redirect handled by caller)"),
            ("FACE_TO_FACE", "Face to face"),
        ],
        string="Default Signature Mode",
        config_parameter="ngsign.default_mode",
        default="BY_MAIL")

    # -- Default visible-signature position ---------------------------------
    ngsign_choose_position = fields.Boolean(
        string="Let the signer place the signature",
        config_parameter="ngsign.choose_position",
        default=False,
        help="If enabled, the signer places the visible signature on the NGSign "
             "page. Disabled (default): the position below is applied "
             "automatically, so the signer just signs without placing a stamp.")
    ngsign_default_page = fields.Integer(
        string="Signature page",
        config_parameter="ngsign.default_page",
        default=1,
        help="Page number where the visible signature is placed (1 = first page).")
    ngsign_default_x = fields.Integer(
        string="Signature X",
        config_parameter="ngsign.default_x",
        default=81,
        help="Horizontal position of the visible signature.")
    ngsign_default_y = fields.Integer(
        string="Signature Y",
        config_parameter="ngsign.default_y",
        default=45,
        help="Vertical position of the visible signature.")
