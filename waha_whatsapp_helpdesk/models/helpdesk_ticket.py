# -*- coding: utf-8 -*-
from odoo import models, fields, _


class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    waha_whatsapp_message_count = fields.Integer(
        compute='_compute_waha_whatsapp_message_count')

    def _compute_waha_whatsapp_message_count(self):
        Message = self.env['waha.whatsapp.message']
        for ticket in self:
            count = 0
            if ticket.partner_id:
                count = Message.search_count([
                    '|',
                    ('partner_id', '=', ticket.partner_id.id),
                    '&', ('res_model', '=', 'helpdesk.ticket'), ('res_id', '=', ticket.id),
                ])
            else:
                count = Message.search_count([
                    ('res_model', '=', 'helpdesk.ticket'), ('res_id', '=', ticket.id)])
            ticket.waha_whatsapp_message_count = count

    def action_view_waha_whatsapp_messages(self):
        self.ensure_one()
        domain = ['|',
                  '&', ('res_model', '=', 'helpdesk.ticket'), ('res_id', '=', self.id),
                  ('partner_id', '=', self.partner_id.id)]
        return {
            'type': 'ir.actions.act_window',
            'name': _('WhatsApp Messages'),
            'res_model': 'waha.whatsapp.message',
            'view_mode': 'list,form',
            'domain': domain,
        }
