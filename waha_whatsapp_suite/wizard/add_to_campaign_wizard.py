# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WahaWhatsappAddToCampaignWizard(models.TransientModel):
    _name = 'waha.whatsapp.add.to.campaign.wizard'
    _description = 'Add Contacts to WhatsApp Campaign'

    mode = fields.Selection([
        ('existing', 'Existing Campaign'),
        ('new', 'New Campaign'),
    ], default='existing', required=True)
    campaign_id = fields.Many2one('waha.whatsapp.campaign', 'Campaign',
                                  domain="[('state', 'in', ['draft', 'scheduled', 'running'])]")
    new_campaign_name = fields.Char('New Campaign Name')
    session_id = fields.Many2one('waha.whatsapp.session', 'Session',
                                 default=lambda self: self.env.company.default_whatsapp_session_id)
    partner_ids = fields.Many2many('res.partner', string='Contacts')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids')
        if active_ids and self.env.context.get('active_model') == 'res.partner':
            res['partner_ids'] = [(6, 0, active_ids)]
        return res

    def action_confirm(self):
        self.ensure_one()
        if not self.partner_ids:
            raise UserError(_("Select at least one contact."))
        if self.mode == 'new':
            if not self.new_campaign_name:
                raise UserError(_("Enter a name for the new campaign."))
            if not self.session_id:
                raise UserError(_("Select a WhatsApp session."))
            campaign = self.env['waha.whatsapp.campaign'].create({
                'name': self.new_campaign_name,
                'session_id': self.session_id.id,
                'recipient_source': 'partners',
                'partner_ids': [(6, 0, self.partner_ids.ids)],
            })
        else:
            if not self.campaign_id:
                raise UserError(_("Select a campaign."))
            campaign = self.campaign_id
            campaign.partner_ids = [(4, p.id) for p in self.partner_ids]
            campaign.action_build_recipients()

        return {
            'type': 'ir.actions.act_window',
            'name': _('WhatsApp Campaign'),
            'res_model': 'waha.whatsapp.campaign',
            'res_id': campaign.id,
            'view_mode': 'form',
            'target': 'current',
        }
