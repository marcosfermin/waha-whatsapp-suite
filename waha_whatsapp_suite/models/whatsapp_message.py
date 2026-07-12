# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import logging
import re

_logger = logging.getLogger(__name__)


class WahaWhatsAppMessage(models.Model):
    _name = 'waha.whatsapp.message'
    _description = 'WhatsApp Message'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Subject', compute='_compute_name', store=True)
    session_id = fields.Many2one('waha.whatsapp.session', 'Session', required=True)
    partner_id = fields.Many2one('res.partner', 'Contact')
    phone_number = fields.Char('Phone Number', required=True)
    chat_id = fields.Char('Chat ID', required=True)

    message_type = fields.Selection([
        ('text', 'Text'),
        ('chat', 'Chat'),
        ('image', 'Image'),
        ('document', 'Document'),
        ('voice', 'Voice'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('sticker', 'Sticker'),
        ('location', 'Location'),
        ('notification', 'Notification'),
    ], string='Type', default='text')

    direction = fields.Selection([
        ('outgoing', 'Outgoing'),
        ('incoming', 'Incoming')
    ], string='Direction', required=True)

    text = fields.Text('Message Text')
    attachment_id = fields.Many2one('ir.attachment', 'Attachment')

    status = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed')
    ], string='Status', default='draft')

    waha_message_id = fields.Char('WAHA Message ID', index=True)
    # Current reaction emoji on this message ('' = none). NOWEB doesn't return
    # reactions in the message list, so we persist them from the live webhook.
    reaction = fields.Char('Reaction')
    error_message = fields.Text('Error Message')

    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company)

    # Optional link to the Odoo record this message relates to (lead, order,
    # ticket, ...). Set when a message is sent from a record or attributed to
    # one by an automation / auto-reply rule.
    res_model = fields.Char('Related Document Model', index=True)
    res_id = fields.Many2oneReference('Related Document ID', model_field='res_model', index=True)

    campaign_id = fields.Many2one('waha.whatsapp.campaign', 'Campaign', ondelete='set null', index=True)
    campaign_recipient_id = fields.Many2one(
        'waha.whatsapp.campaign.recipient', 'Campaign Recipient', ondelete='set null')

    # Set once the inbound side-effects (conversation update, auto-replies) have
    # run, so duplicate webhooks ('message' + 'message.any') don't re-trigger.
    inbound_processed = fields.Boolean('Inbound Handled', default=False, copy=False)
    # Flagged by the webhook when an incoming message needs auto-reply evaluation.
    # A single-threaded cron (cron_run_autoreplies) does the actual sending, so no
    # WhatsApp message is ever sent from inside the concurrent webhook transaction.
    needs_autoreply = fields.Boolean('Auto-reply Pending', default=False, copy=False, index=True)

    def _claim_inbound_processing(self):
        """Atomically mark this message as inbound-processed. Returns True only
        for the caller that wins the claim, so side-effects run exactly once."""
        self.ensure_one()
        # COALESCE: rows inserted via the raw-SQL path below leave this column
        # NULL (Odoo adds no SQL default for default=False), and `NULL = FALSE`
        # is NULL — not TRUE — so a plain `= FALSE` would never match and the
        # claim (hence auto-replies / inbox updates) would never fire.
        self.env.cr.execute(
            "UPDATE waha_whatsapp_message SET inbound_processed = TRUE "
            "WHERE id = %s AND COALESCE(inbound_processed, FALSE) = FALSE RETURNING id",
            (self.id,),
        )
        won = bool(self.env.cr.fetchone())
        if won:
            self.invalidate_recordset(['inbound_processed'])
        return won

    def _claim_autoreply(self):
        """Atomically claim this message for auto-reply (clears needs_autoreply).
        Returns True only for the winner, so the queue job and the fallback cron
        can never both send a reply for the same message."""
        self.ensure_one()
        self.env.cr.execute(
            "UPDATE waha_whatsapp_message SET needs_autoreply = FALSE "
            "WHERE id = %s AND needs_autoreply = TRUE RETURNING id",
            (self.id,),
        )
        won = bool(self.env.cr.fetchone())
        if won:
            self.invalidate_recordset(['needs_autoreply'])
        return won

    def _job_process_autoreply(self):
        """queue_job entry point: send the auto-reply for this message if it is
        still pending. Idempotent — the atomic claim is committed before the
        send, so a job retry (or the fallback cron) never re-sends."""
        self.ensure_one()
        if not self._claim_autoreply():
            return
        # Persist the claim before the irreversible WhatsApp send.
        self.env.cr.commit()
        self.env['waha.whatsapp.autoreply']._run_for_message(self)

    attachment_mimetype = fields.Char(
        string='MIME Type', compute='_compute_attachment_info', store=False)
    attachment_file_size = fields.Char(
        string='File Size', compute='_compute_attachment_info', store=False)
    attachment_download_url = fields.Char(
        string='Download URL', compute='_compute_attachment_info', store=False)

    @api.depends('attachment_id')
    def _compute_attachment_info(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        for rec in self:
            att = rec.attachment_id
            if att:
                rec.attachment_mimetype = att.mimetype or ''
                size = att.file_size or 0
                if size >= 1024 * 1024:
                    rec.attachment_file_size = f"{size / (1024 * 1024):.1f} MB"
                elif size >= 1024:
                    rec.attachment_file_size = f"{size / 1024:.1f} KB"
                else:
                    rec.attachment_file_size = f"{size} B"
                rec.attachment_download_url = (
                    f"{base_url}/web/content/{att.id}/{att.name}?download=true"
                )
            else:
                rec.attachment_mimetype = ''
                rec.attachment_file_size = ''
                rec.attachment_download_url = ''

    @api.depends('partner_id', 'phone_number', 'text')
    def _compute_name(self):
        for record in self:
            if record.partner_id:
                name = record.partner_id.name
            else:
                name = record.phone_number

            if record.text:
                text_preview = record.text[:50] + '...' if len(record.text) > 50 else record.text
                record.name = f"{name}: {text_preview}"
            else:
                record.name = f"{name}: [{record.message_type}]"

    def init(self):
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
                waha_whatsapp_msg_id_uniq
            ON waha_whatsapp_message (waha_message_id)
            WHERE waha_message_id IS NOT NULL
              AND waha_message_id != ''
              AND waha_message_id != 'false'
        """)

    @api.model_create_multi
    def create(self, vals_list):
        if len(vals_list) != 1:
            return super().create(vals_list)
        vals = vals_list[0]
        waha_id = vals.get("waha_message_id")
        if not waha_id or waha_id == "false":
            return super().create(vals_list)

        partner_id = vals.get("partner_id") or None
        phone = vals.get("phone_number") or ""
        text = vals.get("text") or ""
        mtype = vals.get("message_type", "text")
        if partner_id:
            partner = self.env["res.partner"].sudo().browse(partner_id)
            display = partner.name or phone
        else:
            display = phone
        if text:
            preview = text[:50] + "..." if len(text) > 50 else text
            computed_name = "%s: %s" % (display, preview)
        else:
            computed_name = "%s: [%s]" % (display, mtype)

        cr = self.env.cr
        # WAHA delivers the same message on several workers at once; their
        # concurrent INSERTs of the same waha_message_id raise "could not
        # serialize access" instead of cleanly hitting ON CONFLICT. A txn-level
        # advisory lock keyed on the id makes duplicates queue, so only the
        # first inserts and the rest fall through to the search below.
        # ponytail: hashtext gives a 32-bit key — collisions just serialize two
        # unrelated messages briefly, harmless.
        cr.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (waha_id,))
        existing = self.sudo().search([("waha_message_id", "=", waha_id)], limit=1)
        if existing:
            return existing

        new_id = None
        try:
            with cr.savepoint():
                cr.execute("""
                    INSERT INTO waha_whatsapp_message
                        (name, session_id, partner_id, phone_number, chat_id, direction,
                         message_type, status, text, waha_message_id, attachment_id,
                         inbound_processed, create_date, write_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, now(), now())
                    ON CONFLICT (waha_message_id)
                        WHERE waha_message_id IS NOT NULL
                          AND waha_message_id != ''
                          AND waha_message_id != 'false'
                    DO NOTHING
                    RETURNING id
                """, (
                    computed_name,
                    vals.get("session_id"),
                    partner_id,
                    phone,
                    vals.get("chat_id"),
                    vals.get("direction"),
                    mtype,
                    vals.get("status", "delivered"),
                    text or None,
                    waha_id,
                    vals.get("attachment_id") or None,
                ))
                row = cr.fetchone()
                if row:
                    new_id = row[0]
        except Exception:
            pass

        if new_id:
            self.env.cache.invalidate()
            return self.browse(new_id)

        existing = self.sudo().search([("waha_message_id", "=", waha_id)], limit=1)
        return existing or self.browse()

    def write(self, vals):
        res = super().write(vals)
        # Keep campaign recipients in sync with delivery acknowledgements.
        if 'status' in vals:
            recipients = self.mapped('campaign_recipient_id')
            if recipients:
                recipients._sync_from_messages()
        return res

    def _log_on_related_record(self):
        """Mirror the message into the chatter of its related record so the
        WhatsApp exchange is visible from the lead / order / ticket / task."""
        for msg in self:
            if not (msg.res_model and msg.res_id):
                continue
            model = self.env.get(msg.res_model)
            if model is None or not model._fields.get('message_ids'):
                continue
            record = model.browse(msg.res_id).exists()
            if not record:
                continue
            arrow = _("→") if msg.direction == 'outgoing' else _("←")
            body = _("WhatsApp %(arrow)s %(who)s: %(text)s") % {
                'arrow': arrow,
                'who': msg.partner_id.display_name or msg.phone_number,
                'text': msg.text or '[%s]' % msg.message_type,
            }
            record.sudo().message_post(
                body=body,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )

    def action_create_crm_lead_silent(self):
        """Create a CRM lead and link this message to it. Returns the lead."""
        self.ensure_one()
        if 'crm.lead' not in self.env:
            return False
        lead = self.env['crm.lead'].create({
            'name': _("WhatsApp: %s") % (self.partner_id.name or self.phone_number),
            'partner_id': self.partner_id.id or False,
            'phone': self.phone_number,
            'description': self.text or '',
            'type': 'lead',
        })
        self.write({'res_model': 'crm.lead', 'res_id': lead.id})
        self._log_on_related_record()
        return lead

    def action_create_helpdesk_ticket_silent(self):
        """Create a Helpdesk ticket and link this message to it. Returns it.
        Guarded so the base module stays installable without Helpdesk."""
        self.ensure_one()
        if 'helpdesk.ticket' not in self.env:
            return False
        ticket = self.env['helpdesk.ticket'].create({
            'name': _("WhatsApp: %s") % (self.partner_id.name or self.phone_number),
            'partner_id': self.partner_id.id or False,
            'description': self.text or '',
        })
        self.write({'res_model': 'helpdesk.ticket', 'res_id': ticket.id})
        self._log_on_related_record()
        return ticket

    def action_create_crm_lead(self):
        """Create a CRM lead from an incoming WhatsApp message (UI button)."""
        self.ensure_one()
        if 'crm.lead' not in self.env:
            raise UserError(_("The CRM application is not installed."))
        lead = self.action_create_crm_lead_silent()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': lead.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_helpdesk_ticket(self):
        """Create a Helpdesk ticket from an incoming WhatsApp message (UI button)."""
        self.ensure_one()
        if 'helpdesk.ticket' not in self.env:
            raise UserError(_("The Helpdesk application is not installed."))
        ticket = self.action_create_helpdesk_ticket_silent()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.ticket',
            'res_id': ticket.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def get_formview_action(self, access_uid=None):
        self.ensure_one()
        phone = re.sub(r"\D", "", (self.phone_number or "").lstrip("+"))
        return {
            "type": "ir.actions.client",
            "tag": "waha_whatsapp_open_chat",
            "params": {
                "chat_id": "%s@c.us" % phone,
                "session_id": self.session_id.id,
                "phone_number": self.phone_number or "",
                "partner_id": self.partner_id.id or False,
                "partner_name": self.partner_id.name or self.phone_number or "",
            },
        }

    def action_send(self):
        """Send the message"""
        self.ensure_one()

        if self.direction != 'outgoing':
            return

        try:
            if self.message_type == 'text':
                result = self.session_id.send_message(self.chat_id, self.text)
            elif self.message_type == 'voice' and self.attachment_id:
                voice_data = base64.b64encode(self.attachment_id.raw).decode()
                result = self.session_id.send_voice_message(self.chat_id, voice_data, self.attachment_id.name)
            elif self.attachment_id:
                file_data = base64.b64encode(self.attachment_id.raw).decode()
                result = self.session_id.send_message(
                    self.chat_id,
                    self.text,
                    file_data,
                    self.attachment_id.name,
                    self.attachment_id.mimetype
                )

            if result:
                self.status = 'sent'
                self.waha_message_id = result.get('id')

        except Exception as e:
            self.status = 'failed'
            self.error_message = str(e)
