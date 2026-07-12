# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval
import logging

_logger = logging.getLogger(__name__)


class WahaWhatsappCampaign(models.Model):
    _name = 'waha.whatsapp.campaign'
    _description = 'WhatsApp Campaign'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char('Campaign Name', required=True, tracking=True)
    session_id = fields.Many2one(
        'waha.whatsapp.session', 'WhatsApp Session', required=True, tracking=True,
        default=lambda self: self.env.company.default_whatsapp_session_id)
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)

    # Content
    template_id = fields.Many2one('waha.whatsapp.template', 'Template')
    body = fields.Text('Message', help="Message body. Supports {{1}}, {{2}} template "
                                       "variables when a template is selected.")
    attachment_id = fields.Many2one('ir.attachment', 'Attachment')

    # Scheduling / throttling
    scheduled_date = fields.Datetime('Scheduled For', tracking=True,
                                     help="Leave empty to send as soon as the campaign starts.")
    throttle_per_minute = fields.Integer(
        'Messages / minute', default=20,
        help="Maximum number of messages dispatched each time the sender cron runs "
             "(the cron runs once per minute). Keep this modest to avoid being flagged as spam.")

    # Recipient selection
    recipient_source = fields.Selection([
        ('partners', 'Selected Contacts'),
        ('domain', 'Filtered Contacts'),
    ], string='Recipients', default='partners', required=True)
    partner_ids = fields.Many2many('res.partner', string='Contacts')
    recipient_domain = fields.Char('Filter', default='[]',
                                   help="Domain applied on Contacts to build the recipient list.")

    recipient_ids = fields.One2many('waha.whatsapp.campaign.recipient', 'campaign_id', 'Recipients')

    # Statistics (stored so graph/pivot analytics can aggregate them)
    recipient_count = fields.Integer(compute='_compute_stats', string='Recipients', store=True)
    queued_count = fields.Integer(compute='_compute_stats', string='Queued', store=True)
    sent_count = fields.Integer(compute='_compute_stats', string='Sent', store=True)
    delivered_count = fields.Integer(compute='_compute_stats', string='Delivered', store=True)
    read_count = fields.Integer(compute='_compute_stats', string='Read', store=True)
    failed_count = fields.Integer(compute='_compute_stats', string='Failed', store=True)
    skipped_count = fields.Integer(compute='_compute_stats', string='Skipped', store=True)

    @api.depends('recipient_ids.state')
    def _compute_stats(self):
        for c in self:
            states = c.recipient_ids.mapped('state')
            c.recipient_count = len(states)
            c.queued_count = states.count('queued')
            c.sent_count = states.count('sent')
            c.delivered_count = states.count('delivered')
            c.read_count = states.count('read')
            c.failed_count = states.count('failed')
            c.skipped_count = states.count('skipped') + states.count('opted_out')

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.template_id:
            if not self.body:
                self.body = self.template_id.message_text
            if self.template_id.attachment_id and not self.attachment_id:
                self.attachment_id = self.template_id.attachment_id

    # ------------------------------------------------------------------
    # Recipient building
    # ------------------------------------------------------------------
    def _get_target_partners(self):
        self.ensure_one()
        if self.recipient_source == 'partners':
            return self.partner_ids
        domain = safe_eval(self.recipient_domain or '[]')
        return self.env['res.partner'].search(domain)

    def action_build_recipients(self):
        """(Re)build the recipient list from the selected source."""
        Recipient = self.env['waha.whatsapp.campaign.recipient']
        for campaign in self:
            existing = campaign.recipient_ids.filtered(lambda r: r.state != 'queued')
            campaign.recipient_ids.filtered(lambda r: r.state == 'queued').unlink()
            already = existing.mapped('partner_id')
            vals = []
            for partner in campaign._get_target_partners():
                if partner in already:
                    continue
                chat_id = partner.waha_chat_id()
                if partner.waha_whatsapp_opt_out:
                    state = 'opted_out'
                elif not chat_id:
                    state = 'skipped'
                else:
                    state = 'queued'
                vals.append({
                    'campaign_id': campaign.id,
                    'partner_id': partner.id,
                    'phone': partner.waha_whatsapp_number or getattr(partner, 'mobile', '') or partner.phone or '',
                    'chat_id': chat_id,
                    'state': state,
                })
            if vals:
                Recipient.create(vals)
        return True

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------
    def action_schedule(self):
        for campaign in self:
            campaign._check_ready()
            campaign.action_build_recipients()
            campaign.state = 'scheduled' if campaign.scheduled_date else 'running'
        return True

    def action_start(self):
        for campaign in self:
            campaign._check_ready()
            campaign.action_build_recipients()
            campaign.state = 'running'
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})
        return True

    def action_test_send(self):
        """Send the campaign message to the current user (for previewing)."""
        self.ensure_one()
        partner = self.env.user.partner_id
        if not partner.waha_chat_id():
            raise UserError(_("Your own contact has no WhatsApp number to test with."))
        if self.session_id.status != 'working':
            raise UserError(_("The session '%s' is not connected.") % self.session_id.name)
        self._send_to_partner(partner, test=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'message': _('Test message sent.'), 'type': 'success', 'sticky': False},
        }

    def _check_ready(self):
        self.ensure_one()
        if not self.template_id and not self.body:
            raise UserError(_("Add a message body or a template before launching the campaign."))
        if not self.session_id:
            raise UserError(_("Select a WhatsApp session."))

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def _render_body(self, partner):
        self.ensure_one()
        if self.template_id:
            return self.template_id.get_filled_message(partner)
        return self.body or ''

    def _send_to_partner(self, partner, recipient=None, test=False):
        self.ensure_one()
        text = self._render_body(partner)
        message = self.session_id.create_and_send(
            text=text,
            partner=partner,
            attachment=self.attachment_id or (self.template_id.attachment_id if self.template_id else False),
            campaign_recipient=recipient,
            log_on_record=False,
        )
        return message

    def _process_batch(self):
        """Dispatch up to ``throttle_per_minute`` queued recipients. Returns the
        number of messages actually sent."""
        self.ensure_one()
        if self.state != 'running':
            return 0
        if self.session_id.status != 'working':
            _logger.info("Campaign %s waiting: session %s not working", self.name, self.session_id.name)
            return 0

        limit = max(1, self.throttle_per_minute or 20)
        recipients = self.recipient_ids.filtered(lambda r: r.state == 'queued')[:limit]
        sent = 0
        for recipient in recipients:
            partner = recipient.partner_id
            if partner.waha_whatsapp_opt_out:
                recipient.state = 'opted_out'
                continue
            try:
                message = self._send_to_partner(partner, recipient=recipient)
                recipient.message_id = message.id
                recipient.state = 'sent' if message.status == 'sent' else 'failed'
                recipient.error = message.error_message or False
                recipient.sent_date = fields.Datetime.now()
                sent += 1
            except Exception as e:  # noqa: BLE001 - never let one bad number kill the batch
                _logger.exception("Campaign %s failed to send to %s", self.name, partner.display_name)
                recipient.state = 'failed'
                recipient.error = str(e)
            # Commit per message so a later crash doesn't re-send earlier ones.
            self.env.cr.commit()

        if not self.recipient_ids.filtered(lambda r: r.state == 'queued'):
            self.state = 'done'
        return sent

    @api.model
    def cron_process_campaigns(self):
        """Cron entry point: promote due scheduled campaigns and send a batch
        for every running campaign."""
        now = fields.Datetime.now()
        due = self.search([('state', '=', 'scheduled'), ('scheduled_date', '<=', now)])
        for campaign in due:
            campaign.state = 'running'

        running = self.search([('state', '=', 'running')])
        for campaign in running:
            try:
                campaign._process_batch()
            except Exception:  # noqa: BLE001
                _logger.exception("Error processing campaign %s", campaign.name)
                self.env.cr.rollback()

    # ------------------------------------------------------------------
    # Views helpers
    # ------------------------------------------------------------------
    def action_view_messages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Campaign Messages'),
            'res_model': 'waha.whatsapp.message',
            'view_mode': 'list,form',
            'domain': [('campaign_id', '=', self.id)],
            'context': {'search_default_group_status': 1},
        }


class WahaWhatsappCampaignRecipient(models.Model):
    _name = 'waha.whatsapp.campaign.recipient'
    _description = 'WhatsApp Campaign Recipient'
    _rec_name = 'partner_id'

    campaign_id = fields.Many2one('waha.whatsapp.campaign', 'Campaign', required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', 'Contact', required=True)
    phone = fields.Char('Phone')
    chat_id = fields.Char('Chat ID')
    state = fields.Selection([
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped (no number)'),
        ('opted_out', 'Opted-out'),
    ], string='Status', default='queued', index=True)
    message_id = fields.Many2one('waha.whatsapp.message', 'Message', ondelete='set null')
    error = fields.Char('Error')
    sent_date = fields.Datetime('Sent On')

    _campaign_partner_uniq = models.Constraint(
        'unique(campaign_id, partner_id)',
        'A contact can only appear once per campaign.',
    )

    def _sync_from_messages(self):
        """Advance recipient status to match the linked message delivery status."""
        rank = {'queued': 0, 'sent': 1, 'delivered': 2, 'read': 3}
        for rec in self:
            msg = rec.message_id
            if not msg or msg.status not in rank:
                continue
            if rank.get(msg.status, 0) > rank.get(rec.state, 0):
                rec.state = msg.status
