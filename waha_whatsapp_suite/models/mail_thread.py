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

    if HAS_STORE:
        def _thread_to_store(self, store, *args, **kwargs):
            """Odoo 18/19: inject ``canSendWahaWhatsapp`` into the thread store
            so the chatter shows the WhatsApp button on the whitelisted models.

            Signature-agnostic (``*args, **kwargs``) and wrapped in try/except:
            the Store API evolves between minor releases, and a failure here must
            never break the chatter -- worst case the button is simply not shown.
            """
            super()._thread_to_store(store, *args, **kwargs)
            if self._name not in _WHATSAPP_MODELS:
                return
            try:
                store.add(self, {"canSendWahaWhatsapp": True}, as_thread=True)
            except Exception:
                pass
