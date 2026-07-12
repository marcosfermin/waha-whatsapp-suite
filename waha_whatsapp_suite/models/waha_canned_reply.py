# -*- coding: utf-8 -*-
from odoo import models, fields


class WahaWhatsappCannedReply(models.Model):
    """Reusable quick replies surfaced in the chat composer (e.g. '/hello')."""
    _name = 'waha.whatsapp.canned.reply'
    _description = 'WhatsApp Canned Reply'
    _order = 'shortcut'

    name = fields.Char('Title', required=True)
    shortcut = fields.Char('Shortcut', required=True, help="Type this after '/' to insert the reply.")
    body = fields.Text('Message', required=True)
    active = fields.Boolean('Active', default=True)
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('shortcut_uniq', 'unique(shortcut, company_id)', 'The shortcut must be unique.'),
    ]
