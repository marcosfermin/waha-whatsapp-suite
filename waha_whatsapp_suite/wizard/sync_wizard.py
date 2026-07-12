# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WahaWhatsappSyncWizard(models.TransientModel):
    _name = 'waha.whatsapp.sync.wizard'
    _description = 'Sync WhatsApp Data from Phone'

    session_id = fields.Many2one(
        'waha.whatsapp.session', 'Session', required=True,
        default=lambda self: self.env.company.default_whatsapp_session_id)

    sync_contacts = fields.Boolean('Sync Contacts', default=True)
    only_named_contacts = fields.Boolean(
        'Only saved contacts', default=True,
        help="Import only contacts that have a saved name on the phone, so you "
             "don't create a partner for every random number.")

    sync_messages = fields.Boolean('Sync Chats & Messages', default=True)
    message_limit = fields.Integer(
        'Messages per chat', default=100,
        help="How many of the most recent messages to import per chat.")
    include_groups = fields.Boolean('Include group chats', default=False)

    run_mode = fields.Selection([
        ('background', 'In the background (recommended)'),
        ('now', 'Now (may take a while)'),
    ], string='Run', default='background', required=True,
        help="Background sync is handled by a scheduled job that imports a few "
             "chats at a time, so it never blocks or times out.")
    chats_per_run = fields.Integer(
        'Chats per run', default=10,
        help="For a background sync: how many chats are imported each time the "
             "scheduler runs (every couple of minutes).")

    @api.constrains('message_limit')
    def _check_limit(self):
        for wiz in self:
            if wiz.sync_messages and wiz.message_limit <= 0:
                raise UserError(_("Messages per chat must be greater than zero."))

    def action_sync(self):
        self.ensure_one()
        session = self.session_id
        if not session:
            raise UserError(_("Select a session."))
        if session.status != 'working':
            raise UserError(_("The session '%s' is not connected (status: %s).")
                            % (session.name, session.status))
        if not self.sync_contacts and not self.sync_messages:
            raise UserError(_("Select at least one thing to sync."))

        if self.run_mode == 'background':
            job = self.env['waha.whatsapp.sync.job'].create({
                'session_id': session.id,
                'sync_contacts': self.sync_contacts,
                'only_named_contacts': self.only_named_contacts,
                'sync_messages': self.sync_messages,
                'message_limit': self.message_limit,
                'include_groups': self.include_groups,
                'chats_per_run': self.chats_per_run,
                'state': 'queued',
            })
            return {
                'type': 'ir.actions.act_window',
                'name': _('Sync Job'),
                'res_model': 'waha.whatsapp.sync.job',
                'res_id': job.id,
                'view_mode': 'form',
                'target': 'current',
            }

        parts = []
        if self.sync_contacts:
            res = session.sync_contacts(only_named=self.only_named_contacts)
            parts.append(_("Contacts: %(created)s created, %(updated)s updated, %(skipped)s skipped")
                         % res)
        if self.sync_messages:
            res = session.sync_messages(
                message_limit=self.message_limit, include_groups=self.include_groups)
            parts.append(_("Messages: %(imported)s imported from %(chats)s chats (%(skipped)s already present)")
                         % res)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync complete'),
                'message': ' • '.join(parts),
                'type': 'success',
                'sticky': True,
            },
        }
