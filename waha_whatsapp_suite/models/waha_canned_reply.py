# -*- coding: utf-8 -*-
from odoo import models, fields, api


class WahaWhatsappCannedReply(models.Model):
    """Reusable quick replies surfaced in the chat composer (e.g. '/hello')."""
    _name = 'waha.whatsapp.canned.reply'
    _description = 'WhatsApp Canned Reply'
    _order = 'shortcut'

    name = fields.Char('Title', required=True)
    shortcut = fields.Char('Shortcut', required=True, help="Type /shortcut in the chat composer to insert the reply.")
    body = fields.Text('Message', required=True)
    active = fields.Boolean('Active', default=True)
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company)

    _shortcut_uniq = models.Constraint(
        'unique(shortcut, company_id)',
        'The shortcut must be unique.',
    )

    @api.model
    def expand(self, text):
        """If ``text`` starts with '/shortcut', replace that token with the
        canned reply body (any trailing text is kept). Returns the text
        unchanged when it isn't a canned-reply command."""
        if not text:
            return text
        stripped = text.strip()
        if not stripped.startswith('/'):
            return text
        first = stripped.split(None, 1)[0]      # e.g. '/hello'
        shortcut = first[1:]
        if not shortcut:
            return text
        reply = self.search([
            ('shortcut', '=', shortcut),
            ('active', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not reply:
            return text
        rest = stripped[len(first):].strip()
        return reply.body + ((' ' + rest) if rest else '')
