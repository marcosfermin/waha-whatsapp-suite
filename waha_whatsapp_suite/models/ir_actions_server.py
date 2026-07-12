# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    state = fields.Selection(
        selection_add=[('waha_whatsapp', 'Send WhatsApp')],
        ondelete={'waha_whatsapp': 'cascade'},
    )
    waha_session_id = fields.Many2one('waha.whatsapp.session', 'WhatsApp Session')
    waha_template_id = fields.Many2one('waha.whatsapp.template', 'WhatsApp Template')
    waha_body = fields.Text('WhatsApp Message')
    waha_partner_field = fields.Char(
        'Contact Field', default='partner_id',
        help="Dotted path from the triggering record to the res.partner to message "
             "(e.g. 'partner_id', 'partner_id.commercial_partner_id'). Leave 'id' to "
             "message the record itself when it is a contact.")

    @api.constrains('state', 'waha_template_id', 'waha_body')
    def _check_waha_content(self):
        for action in self:
            if action.state == 'waha_whatsapp' and not action.waha_template_id and not action.waha_body:
                raise ValidationError(_("A WhatsApp action needs a template or a message body."))

    def _waha_resolve_partner(self, record):
        """Resolve the target res.partner from a triggering record."""
        self.ensure_one()
        path = (self.waha_partner_field or 'partner_id').strip()
        if path in ('id', '') and record._name == 'res.partner':
            return record
        value = record
        for part in path.split('.'):
            if not value:
                return self.env['res.partner']
            value = value[part] if part in value._fields else False
        if value and value._name == 'res.partner':
            return value[:1]
        return self.env['res.partner']

    def _run_action_waha_whatsapp_multi(self, eval_context=None):
        """Executed by automation rules / manual server actions. Sends a
        WhatsApp message to each triggering record's contact."""
        records = self.env.context.get('active_records')
        if records is None and eval_context:
            records = eval_context.get('records') or eval_context.get('record')
        if records is None:
            model = self.env.get(self.model_name)
            active_ids = self.env.context.get('active_ids')
            if model is not None and active_ids:
                records = model.browse(active_ids)
        if not records:
            return False

        session = self.waha_session_id or self.env.company.default_whatsapp_session_id
        if not session:
            _logger.warning("WhatsApp server action %s has no session configured", self.name)
            return False

        for record in records:
            partner = self._waha_resolve_partner(record)
            if not partner or not partner.waha_chat_id():
                _logger.info("WhatsApp action %s: no number for %s", self.name, record)
                continue
            if partner.waha_whatsapp_opt_out:
                continue
            if session.status != 'working':
                _logger.info("WhatsApp action %s skipped: session not connected", self.name)
                break
            text = (self.waha_template_id.get_filled_message(record)
                    if self.waha_template_id else (self.waha_body or ''))
            try:
                session.create_and_send(
                    text=text,
                    partner=partner,
                    attachment=self.waha_template_id.attachment_id if self.waha_template_id else False,
                    res_model=record._name,
                    res_id=record.id,
                )
            except Exception:  # noqa: BLE001
                _logger.exception("WhatsApp server action %s failed for %s", self.name, record)
        return False
