# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

    waha_whatsapp_number = fields.Char(
        'WhatsApp Number',
        compute='_compute_waha_whatsapp_number',
        store=True,
        help="WhatsApp phone number (auto-computed from mobile/phone)"
    )
    waha_whatsapp_message_ids = fields.One2many(
        'waha.whatsapp.message',
        'partner_id',
        'WhatsApp Messages',
        groups='waha_whatsapp_suite.group_waha_whatsapp_user',
    )
    waha_whatsapp_message_count = fields.Integer(
        'WhatsApp Message Count',
        compute='_compute_waha_whatsapp_message_count',
        groups='waha_whatsapp_suite.group_waha_whatsapp_user',
    )
    waha_whatsapp_opt_out = fields.Boolean(
        'WhatsApp Opt-out',
        help="If set, this contact will be excluded from WhatsApp campaigns and "
             "automated messages. Set automatically when a contact replies with a "
             "stop keyword.",
    )
    waha_synced_name = fields.Char(
        'WhatsApp Synced Name', copy=False,
        help="Internal: the phone's saved name as of the last sync. Used to detect "
             "whether this contact's name was edited in Odoo, so a phone-side rename "
             "only overwrites names that were not manually changed.",
    )

    def waha_chat_id(self):
        """Return the WhatsApp chat id (e.g. '2011...@c.us') for this partner,
        or an empty string when no usable number is available."""
        self.ensure_one()
        # Odoo 19 removed res.partner.mobile — read it defensively so the same
        # code works on 17/18 (mobile present) and 19 (mobile absent).
        number = self.waha_whatsapp_number or getattr(self, 'mobile', '') or self.phone or ''
        digits = re.sub(r'\D', '', number)
        if not digits:
            return ''
        return '%s@c.us' % digits

    @api.depends(lambda self: [f for f in ('mobile', 'phone') if f in self._fields])
    def _compute_waha_whatsapp_number(self):
        """Compute WhatsApp number from mobile or phone, removing spaces and formatting"""
        for partner in self:
            number = getattr(partner, 'mobile', '') or partner.phone or ''
            if number:
                # Remove spaces, dashes, parentheses, and other formatting
                cleaned_number = re.sub(r'[\s\-\(\)\.]', '', number)

                # Ensure number starts with + for international format
                # If it doesn't, leave it as is but user will get error when sending
                if cleaned_number and not cleaned_number.startswith('+'):
                    # Try to detect and warn, but don't modify
                    # User should fix the mobile/phone field to include country code
                    partner.waha_whatsapp_number = cleaned_number
                else:
                    partner.waha_whatsapp_number = cleaned_number
            else:
                partner.waha_whatsapp_number = False

    @api.depends('waha_whatsapp_message_ids')
    def _compute_waha_whatsapp_message_count(self):
        for partner in self:
            partner.waha_whatsapp_message_count = len(partner.waha_whatsapp_message_ids)

    def action_send_whatsapp(self):
        """Open wizard to send WhatsApp message"""
        self.ensure_one()

        if not self.waha_whatsapp_number:
            raise UserError(_("No WhatsApp number available for this contact. Please add a mobile or phone number."))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Send WhatsApp Message',
            'res_model': 'waha.whatsapp.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.id,
                'default_phone_number': self.waha_whatsapp_number,
            }
        }

    def action_view_whatsapp_messages(self):
        """View WhatsApp messages for this partner"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'WhatsApp Messages',
            'res_model': 'waha.whatsapp.message',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id}
        }
