# -*- coding: utf-8 -*-
from odoo import models, fields, _


class ProjectTask(models.Model):
    _inherit = 'project.task'

    waha_whatsapp_message_count = fields.Integer(
        compute='_compute_waha_whatsapp_message_count')

    def _compute_waha_whatsapp_message_count(self):
        Message = self.env['waha.whatsapp.message']
        for task in self:
            count = 0
            if task.partner_id:
                count = Message.search_count([
                    '|',
                    ('partner_id', '=', task.partner_id.id),
                    '&', ('res_model', '=', 'project.task'), ('res_id', '=', task.id),
                ])
            task.waha_whatsapp_message_count = count

    def action_view_waha_whatsapp_messages(self):
        self.ensure_one()
        domain = ['|', ('partner_id', '=', self.partner_id.id),
                  '&', ('res_model', '=', 'project.task'), ('res_id', '=', self.id)]
        return {
            'type': 'ir.actions.act_window',
            'name': _('WhatsApp Messages'),
            'res_model': 'waha.whatsapp.message',
            'view_mode': 'list,form',
            'domain': domain,
        }
