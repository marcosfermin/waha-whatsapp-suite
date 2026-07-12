# -*- coding: utf-8 -*-
from odoo import models

try:
    from odoo.addons.mail.tools.discuss import Store
    HAS_STORE = True
except ImportError:
    HAS_STORE = False


_WHATSAPP_MODELS = [
    'res.partner',
    'crm.lead',
    'sale.order',
    'account.move',
    'res.users',
    'purchase.order',
    'project.project',
    'project.task',
    'helpdesk.ticket',
]


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _get_mail_thread_data(self, request_list):
        """Odoo 17: inject canSendWahaWhatsapp into thread data dict."""
        result = super()._get_mail_thread_data(request_list)
        result['canSendWahaWhatsapp'] = self._name in _WHATSAPP_MODELS
        return result

    if HAS_STORE:
        def _thread_to_store(self, store: Store, /, *, request_list=None, **kwargs):
            """Odoo 18+: inject canSendWahaWhatsapp into thread store."""
            super()._thread_to_store(store, request_list=request_list, **kwargs)
            if request_list:
                store.add(
                    self,
                    {"canSendWahaWhatsapp": self._name in _WHATSAPP_MODELS},
                    as_thread=True,
                )
