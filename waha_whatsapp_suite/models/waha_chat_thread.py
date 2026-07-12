# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class WahaWhatsappChatThread(models.Model):
    """A lightweight conversation record (one per session + chat) that powers a
    shared-inbox workflow: assignment, status and unread tracking. It is fed
    from the inbound webhook and does not replace the live chat UI."""
    _name = 'waha.whatsapp.chat.thread'
    _description = 'WhatsApp Conversation'
    _order = 'last_message_date desc'

    session_id = fields.Many2one('waha.whatsapp.session', 'Session', required=True, ondelete='cascade', index=True)
    chat_id = fields.Char('Chat ID', required=True, index=True)
    partner_id = fields.Many2one('res.partner', 'Contact')
    phone_number = fields.Char('Phone')
    name = fields.Char('Contact', compute='_compute_name', store=True)

    user_id = fields.Many2one('res.users', 'Assigned To', tracking=True)
    stage = fields.Selection([
        ('open', 'Open'),
        ('pending', 'Pending'),
        ('resolved', 'Resolved'),
    ], string='Status', default='open', index=True)

    last_message = fields.Text('Last Message')
    last_message_date = fields.Datetime('Last Activity', index=True)
    unread_count = fields.Integer('Unread', default=0)
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company)

    _session_chat_uniq = models.Constraint(
        'unique(session_id, chat_id)',
        'A conversation already exists for this session and chat.',
    )

    @api.depends('partner_id', 'partner_id.name', 'phone_number', 'chat_id')
    def _compute_name(self):
        for rec in self:
            rec.name = (rec.partner_id.name or rec.phone_number
                        or (rec.chat_id or '').split('@')[0])

    @api.model
    def _get_or_create(self, session, chat_id, partner=None, phone=None):
        thread = self.search([('session_id', '=', session.id), ('chat_id', '=', chat_id)], limit=1)
        if not thread:
            thread = self.create({
                'session_id': session.id,
                'chat_id': chat_id,
                'partner_id': partner.id if partner else False,
                'phone_number': phone or (partner.waha_whatsapp_number if partner else ''),
            })
        elif partner and not thread.partner_id:
            thread.partner_id = partner.id
        return thread

    @api.model
    def _touch_from_message(self, message):
        """Update / create the conversation from a stored message."""
        if not message or not message.chat_id:
            return
        thread = self._get_or_create(
            message.session_id, message.chat_id, message.partner_id, message.phone_number)
        vals = {
            'last_message': (message.text or '[%s]' % message.message_type)[:200],
            'last_message_date': message.create_date or fields.Datetime.now(),
        }
        if message.direction == 'incoming':
            vals['unread_count'] = thread.unread_count + 1
            if thread.stage == 'resolved':
                vals['stage'] = 'open'
        thread.write(vals)
        return thread

    # ------------------------------------------------------------------
    def action_open_chat(self):
        self.ensure_one()
        self.unread_count = 0
        return {
            'type': 'ir.actions.client',
            'tag': 'waha_whatsapp_open_chat',
            'params': {
                'chat_id': self.chat_id,
                'session_id': self.session_id.id,
                'phone_number': self.phone_number or '',
                'partner_id': self.partner_id.id or False,
                'partner_name': self.partner_id.name or self.phone_number or '',
            },
        }

    def action_assign_to_me(self):
        self.write({'user_id': self.env.uid})

    def action_mark_resolved(self):
        self.write({'stage': 'resolved'})

    def action_mark_open(self):
        self.write({'stage': 'open', 'unread_count': 0})
