# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging
import re

_logger = logging.getLogger(__name__)


class WahaWhatsappAutoreply(models.Model):
    _name = 'waha.whatsapp.autoreply'
    _description = 'WhatsApp Auto-reply Rule'
    _order = 'sequence, id'

    name = fields.Char('Rule Name', required=True)
    active = fields.Boolean('Active', default=True)
    sequence = fields.Integer('Priority', default=10,
                              help="Rules are evaluated in ascending order. "
                                   "The first matching rule wins.")
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company)

    session_id = fields.Many2one(
        'waha.whatsapp.session', 'Session',
        help="Restrict this rule to one session. Leave empty to apply to all sessions.")

    match_type = fields.Selection([
        ('contains', 'Contains'),
        ('equals', 'Equals'),
        ('starts_with', 'Starts with'),
        ('regex', 'Regular Expression'),
        ('any', 'Any message'),
    ], string='Match', default='contains', required=True)
    keyword = fields.Char('Keyword / Pattern',
                          help="Comma-separated keywords (any match triggers), or a "
                               "regular expression when Match = Regular Expression.")
    case_sensitive = fields.Boolean('Case sensitive', default=False)

    # Business hours restriction
    only_business_hours = fields.Boolean('Only in business hours')
    hour_from = fields.Float('From', default=9.0)
    hour_to = fields.Float('To', default=17.0)

    stop_after_match = fields.Boolean(
        'Stop processing', default=True,
        help="If set, no lower-priority rule runs once this one matches.")

    # Actions
    reply_template_id = fields.Many2one('waha.whatsapp.template', 'Reply Template')
    reply_body = fields.Text('Reply Message')
    reply_attachment_ids = fields.Many2many(
        'ir.attachment', 'waha_autoreply_attachment_rel', 'autoreply_id', 'attachment_id',
        string='Reply Attachments',
        help="Images, documents or audio sent with the reply. The reply text is sent first "
             "as its own message, then each attachment follows as a separate message.")
    set_opt_out = fields.Boolean('Mark contact as opted-out',
                                 help="Use for STOP / unsubscribe keywords.")
    clear_opt_out = fields.Boolean('Re-subscribe contact',
                                   help="Use for START / subscribe keywords.")
    tag_ids = fields.Many2many('res.partner.category', string='Add Tags to Contact')
    create_lead = fields.Boolean('Create CRM Lead')
    create_ticket = fields.Boolean('Create Helpdesk Ticket')
    assign_user_id = fields.Many2one('res.users', 'Assign Conversation To')

    hit_count = fields.Integer('Triggered', default=0, readonly=True)

    # ------------------------------------------------------------------
    def _matches(self, text):
        self.ensure_one()
        if self.match_type == 'any':
            return True
        if not text:
            return False
        haystack = text if self.case_sensitive else text.lower()
        pattern = self.keyword or ''
        if not self.case_sensitive:
            pattern = pattern.lower()

        if self.match_type == 'regex':
            try:
                flags = 0 if self.case_sensitive else re.IGNORECASE
                return bool(re.search(self.keyword or '', text or '', flags))
            except re.error:
                _logger.warning("Invalid regex in auto-reply rule %s", self.name)
                return False

        keywords = [k.strip() for k in pattern.split(',') if k.strip()]
        for kw in keywords:
            if self.match_type == 'equals' and haystack.strip() == kw:
                return True
            if self.match_type == 'contains' and kw in haystack:
                return True
            if self.match_type == 'starts_with' and haystack.strip().startswith(kw):
                return True
        return False

    def _within_hours(self):
        self.ensure_one()
        if not self.only_business_hours:
            return True
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        current = now.hour + now.minute / 60.0
        return self.hour_from <= current <= self.hour_to

    @api.model
    def cron_run_autoreplies(self):
        """Send auto-replies for messages the webhook flagged. Runs single-
        threaded from a scheduled action, so the (irreversible) WhatsApp send
        never happens inside the concurrent, auto-retried webhook transaction —
        which is what previously caused reply floods."""
        Message = self.env['waha.whatsapp.message']
        pending = Message.search([('needs_autoreply', '=', True)], order='id', limit=200)
        if pending:
            _logger.info("Auto-reply cron: %s message(s) to process", len(pending))
        for msg in pending:
            # Atomically claim the message (also handles the race with the
            # queue_job worker) and COMMIT *before* sending, so the reply is
            # never sent twice — at worst a single reply is missed on error.
            if not msg._claim_autoreply():
                continue
            self.env.cr.commit()
            try:
                self._run_for_message(msg)
            except Exception:  # noqa: BLE001
                _logger.exception("Auto-reply cron failed for message %s", msg.id)
                self.env.cr.rollback()
            self.env.cr.commit()

    @api.model
    def _run_for_message(self, message):
        """Evaluate active rules against an incoming message and apply the
        first matching rule's actions. Called from the inbound webhook."""
        if not message or message.direction != 'incoming':
            return
        rules = self.search([('active', '=', True)])
        text = message.text or ''
        _logger.info("Auto-reply: evaluating %s active rule(s) for message %s (text=%r)",
                     len(rules), message.id, text[:60])
        matched_any = False
        for rule in rules:
            if rule.session_id and rule.session_id != message.session_id:
                continue
            if not rule._within_hours():
                continue
            if not rule._matches(text):
                continue
            matched_any = True
            _logger.info("Auto-reply rule '%s' matched message %s", rule.name, message.id)
            try:
                rule._apply(message)
            except Exception:  # noqa: BLE001
                _logger.exception("Auto-reply rule %s failed on message %s", rule.name, message.id)
            rule.hit_count += 1
            if rule.stop_after_match:
                break
        if not matched_any:
            _logger.info("Auto-reply: no rule matched message %s", message.id)

    def _apply(self, message):
        self.ensure_one()
        partner = message.partner_id

        if self.set_opt_out and partner:
            partner.waha_whatsapp_opt_out = True
        if self.clear_opt_out and partner:
            partner.waha_whatsapp_opt_out = False

        if self.tag_ids and partner:
            partner.category_id = [(4, t.id) for t in self.tag_ids]

        if self.create_lead and 'crm.lead' in self.env:
            lead = message.action_create_crm_lead_silent()
            if lead and self.assign_user_id:
                lead.user_id = self.assign_user_id.id

        if self.create_ticket and 'helpdesk.ticket' in self.env:
            ticket = message.action_create_helpdesk_ticket_silent()
            if ticket and self.assign_user_id and 'user_id' in ticket._fields:
                ticket.user_id = self.assign_user_id.id

        # Update the shared-inbox conversation assignment.
        if self.assign_user_id:
            thread = self.env['waha.whatsapp.chat.thread']._get_or_create(
                message.session_id, message.chat_id, partner)
            thread.user_id = self.assign_user_id.id

        # Auto reply last so the record links already exist.
        reply_text = ''
        attachments = self.env['ir.attachment']
        if self.reply_template_id:
            reply_text = self.reply_template_id.get_filled_message(partner)
            attachments |= self.reply_template_id.attachment_id
        elif self.reply_body:
            reply_text = self.reply_body
        attachments |= self.reply_attachment_ids

        if not (reply_text or attachments):
            return
        session = message.session_id

        # Don't refresh the session status here — that writes to the shared
        # session row and, under the concurrency of inbound webhooks, causes
        # serialization failures / retries (which resend the reply). A received
        # message already proves the session is live, so just skip on the rare
        # stale-not-working case rather than forcing a write.
        if session.status != 'working':
            _logger.warning("Auto-reply '%s': session '%s' not working (status=%s) — reply skipped",
                            self.name, session.name, session.status)
            return

        # Reply to the contact's real number. WhatsApp increasingly delivers the
        # inbound 'from' as an @lid address that WAHA cannot send to, so prefer
        # the resolved phone (-> digits@c.us) and only fall back to a @c.us chat id.
        reply_phone = message.phone_number or ''
        reply_chat_id = message.chat_id if (message.chat_id or '').endswith('@c.us') else None
        if not reply_phone and not reply_chat_id:
            reply_chat_id = message.chat_id  # last resort (e.g. group @g.us)

        def _send(text, attachment):
            session.create_and_send(
                text=text,
                partner=partner,
                phone=reply_phone or None,
                chat_id=reply_chat_id,
                attachment=attachment or False,
                log_on_record=False,
            )

        # Send the text as its own message first, then each file separately.
        if reply_text:
            _send(reply_text, False)
        for att in attachments:
            _send('', att)
