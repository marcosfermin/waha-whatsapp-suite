from odoo import models


class WahaWhatsappSession(models.Model):
    _inherit = 'waha.whatsapp.session'

    def action_open_waha_chat(self):
        """Open the WhatsApp-Web-style chat client action for this session."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'waha_whatsapp_chat.float_open',
            'name': 'WhatsApp Chat',
            'target': 'new',
            'context': {
                'session_id': self.id,
                'session_name': self.name,
            },
        }
