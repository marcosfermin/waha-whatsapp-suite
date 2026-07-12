# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import base64
import logging

_logger = logging.getLogger(__name__)


class WahaWhatsappSession(models.Model):
    _name = 'waha.whatsapp.session'
    _description = 'WAHA WhatsApp Session'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Session Name', required=True, tracking=True, help="Unique session identifier")
    waha_server_url = fields.Char('WAHA Server URL', required=True, default='http://localhost:3000', tracking=True)
    session_id = fields.Char('Session ID', tracking=True, help="WAHA session identifier")
    status = fields.Selection([
        ('stopped', 'Stopped'),
        ('starting', 'Starting'),
        ('scan_qr_code', 'Scan QR Code'),
        ('working', 'Working'),
        ('failed', 'Failed')
    ], string='Status', default='stopped', readonly=True, tracking=True)

    qr_code = fields.Text('QR Code', readonly=True)
    qr_code_image = fields.Binary('QR Code Image', readonly=True)

    phone_number = fields.Char('Phone Number', readonly=True, tracking=True)
    profile_name = fields.Char('Profile Name', readonly=True, tracking=True)
    profile_picture = fields.Binary('Profile Picture', readonly=True)

    webhook_url = fields.Char(string='Webhook URL', tracking=True, help="URL to receive incoming messages",
                              default=lambda self: self._get_default_webhook_url()
                              )
    webhook_events = fields.Char(string='Webhook Events', default='message.any,message.ack,session.status',
                                 tracking=True, help="Comma-separated list of events to receive")
    api_key = fields.Char('API Key', help="WAHA API Key for authentication")

    engine = fields.Selection([
        ('WEBJS', 'WEBJS (Browser based)'),
        ('NOWEB', 'NOWEB (WebSocket NodeJS)'),
        ('GOWS', 'GOWS (WebSocket Go)')
    ], string='Engine', default='NOWEB', tracking=True)

    active = fields.Boolean('Active', default=True, tracking=True)
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company)

    last_sync = fields.Datetime('Last Sync', readonly=True)
    last_sync_contacts = fields.Datetime('Last Contacts Sync', readonly=True)
    last_sync_messages = fields.Datetime('Last Messages Sync', readonly=True)
    error_message = fields.Text('Error Message', readonly=True)

    # Statistics (computed from actual message records)
    messages_sent = fields.Integer(
        'Messages Sent', compute='_compute_message_counts', store=False)
    messages_received = fields.Integer(
        'Messages Received', compute='_compute_message_counts', store=False)

    notify_user_ids = fields.Many2many('res.users', string='Notify Users',
                                       help="Users to notify when a new WhatsApp message is received")

    message_ids = fields.One2many(
        'waha.whatsapp.message', 'session_id', string='Messages')

    @api.depends('message_ids.direction')
    def _compute_message_counts(self):
        for session in self:
            session.messages_sent = len(
                session.message_ids.filtered(lambda m: m.direction == 'outgoing'))
            session.messages_received = len(
                session.message_ids.filtered(lambda m: m.direction == 'incoming'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('session_id'):
                vals['session_id'] = vals.get('name', '').lower().replace(' ', '_')

        records = super().create(vals_list)

        for record in records:
            _logger.info(f"WhatsApp Session created: {record.name} (ID: {record.id})")
            record.message_post(
                body=_("WhatsApp session '%s' has been created successfully.") % record.name,
                subject=_("Session Created")
            )

        return records

    _LOCK_NAMESPACE = 0x57414841  # 'WAHA'

    def write(self, vals):
        if 'status' in vals:
            for rec in self:
                self.env.cr.execute(
                    "SELECT pg_advisory_xact_lock(%s, %s)",
                    (self._LOCK_NAMESPACE, rec.id),
                )

        res = super().write(vals)

        if 'status' in vals:
            _logger.info("Session %s status changed to: %s", self.mapped('name'), vals['status'])

        if 'webhook_url' in vals:
            _logger.info("Session %s webhook URL updated to: %s", self.mapped('name'), vals['webhook_url'])

        return res

    def unlink(self):
        for record in self:
            _logger.warning(f"WhatsApp Session deleted: {record.name} (ID: {record.id})")
        return super().unlink()

    def _make_api_request(self, endpoint, method='GET', data=None, params=None):
        """Make API request to WAHA server"""
        try:
            url = f"{self.waha_server_url.rstrip('/')}/api/{endpoint.lstrip('/')}"
            headers = {'Content-Type': 'application/json'}

            if self.api_key:
                headers['X-Api-Key'] = self.api_key

            _logger.debug(f"WAHA API Request: {method} {url}")

            if method == 'GET':
                response = requests.get(url, params=params, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            if response.status_code not in [200, 201]:
                _logger.error(f"WAHA API Error Response: {response.status_code} - {response.text}")
                try:
                    err_body = response.json()
                except Exception:
                    err_body = response.text
                raise UserError(str(err_body))

            _logger.debug(f"WAHA API Success: {method} {url} - Status: {response.status_code}")

            if response.headers.get('Content-Type', '').startswith('application/json'):
                return response.json()
            else:
                return response.content

        except requests.exceptions.RequestException as e:
            _logger.error(f"WAHA API request failed for session id={self.id}: {e}")
            self.error_message = str(e)
            raise UserError(_("Failed to connect to WAHA server: %s") % str(e))

    def action_start_session(self):
        """Start WhatsApp session"""
        self.ensure_one()

        session_id = self.id
        _logger.info(f"Starting WhatsApp session id={session_id}")

        self.env.cr.flush()

        waha_session_id = self.session_id
        webhook_url = self.webhook_url
        webhook_events = self.webhook_events

        try:
            data = {
                'name': waha_session_id,
                'start': True,
                'config': {
                    'noweb': {
                        'store': {
                            'enabled': True,
                            'full_sync': True,
                        }
                    }
                }
            }

            if webhook_url:
                data['config']['webhooks'] = [{
                    'url': webhook_url,
                    'events': webhook_events.split(',') if webhook_events else ['message']
                }]

            # Try POST first; if session already exists on WAHA use PUT (config only, no restart)
            try:
                self._make_api_request('sessions', 'POST', data)
            except Exception as post_err:
                err_body = post_err.args[0] if post_err.args else {}
                status_code = err_body.get('statusCode') if isinstance(err_body, dict) else None
                if status_code == 422:
                    _logger.info(f"Session {waha_session_id} already exists on WAHA, updating config only")
                    put_data = {k: v for k, v in data.items() if k != 'start'}
                    self._make_api_request(f'sessions/{waha_session_id}', 'PUT', put_data)
                else:
                    raise

            self.status = 'starting'
            self.error_message = False

            _logger.info(f"Session id={session_id} started successfully")

            self.message_post(
                body=_("WhatsApp session started successfully. Please scan QR code if required."),
                subject=_("Session Started")
            )

        except Exception as e:
            _logger.error(f"Failed to start session id={session_id}: {e}")
            self.invalidate_recordset()
            self.status = 'failed'
            self.error_message = str(e)

            self.message_post(
                body=_("Failed to start session: %s") % str(e),
                subject=_("Session Start Failed")
            )

            raise UserError(_("Failed to start session: %s") % str(e))

    def action_stop_session(self):
        """Stop WhatsApp session"""
        self.ensure_one()

        session_id = self.id
        waha_session_id = self.session_id
        _logger.info(f"Stopping WhatsApp session id={session_id}")

        try:
            self._make_api_request(f'sessions/{waha_session_id}', 'DELETE')
        except Exception as e:
            _logger.error(f"Failed to stop session id={session_id}: {e}")
            raise UserError(_("Failed to stop session: %s") % str(e))

        self.status = 'stopped'
        self.qr_code = False
        self.qr_code_image = False
        self.error_message = False

        _logger.info(f"Session id={session_id} stopped successfully")
        self.message_post(
            body=_("WhatsApp session stopped successfully."),
            subject=_("Session Stopped")
        )

    def _fetch_qr_image(self):
        """Fetch the live pairing QR code as PNG bytes from WAHA.

        Uses the engine-agnostic ``/api/{session}/auth/qr`` endpoint (works for
        NOWEB/GOWS, not just the browser-based WEBJS engine). Falls back to the
        WEBJS ``/screenshot`` endpoint. Returns PNG bytes or None.
        """
        self.ensure_one()
        base = self.waha_server_url.rstrip('/')
        headers = {'Accept': 'image/png'}
        if self.api_key:
            headers['X-Api-Key'] = self.api_key

        # Primary: dedicated auth QR endpoint.
        try:
            url = f"{base}/api/{self.session_id}/auth/qr"
            resp = requests.get(url, headers=headers, params={'format': 'image'}, timeout=15)
            ct = resp.headers.get('Content-Type', '')
            if resp.status_code == 200 and resp.content:
                if ct.startswith('application/json'):
                    data = resp.json()
                    b64 = data.get('data') if isinstance(data, dict) else None
                    if b64:
                        return base64.b64decode(b64)
                elif not ct.startswith('text/html'):
                    return resp.content
            else:
                _logger.debug("auth/qr returned %s for session %s", resp.status_code, self.name)
        except requests.exceptions.RequestException as e:
            _logger.debug("auth/qr request failed for session %s: %s", self.name, e)

        # Fallback: browser screenshot (WEBJS only).
        if self.engine == 'WEBJS':
            try:
                screenshot = self._make_api_request('screenshot', 'GET', params={'session': self.session_id})
                if isinstance(screenshot, bytes):
                    return screenshot
            except Exception as e:  # noqa: BLE001
                _logger.debug("screenshot fallback failed for session %s: %s", self.name, e)

        return None

    def action_get_qr_code(self):
        """Fetch the QR code and store it on the record so it renders in Odoo."""
        self.ensure_one()

        _logger.info(f"Fetching QR code for session: {self.name}")

        # Refresh status first so we don't ask for a QR on a connected session.
        self.action_refresh_status()
        if self.status == 'working':
            self.qr_code_image = False
            self.message_post(
                body=_("Session is already connected — no QR code needed."),
                subject=_("Already Connected"),
            )
            return

        try:
            content = self._fetch_qr_image()
            if content:
                self.qr_code_image = base64.b64encode(content)
                self.error_message = False
                _logger.info(f"QR Code retrieved successfully for session {self.name}")
                self.message_post(
                    body=_("QR Code retrieved. Please scan it to authenticate."),
                    subject=_("QR Code Retrieved"),
                )
            else:
                _logger.debug(f"No QR data received for session {self.name}")
                self.message_post(
                    body=_("No QR code available yet. The session may still be starting — try again in a moment."),
                    subject=_("QR Code Request"),
                )
        except Exception as e:
            self.error_message = str(e)
            _logger.error(f"Failed to get QR code for {self.name}: {e}")
            self.message_post(
                body=_("Failed to get QR code: %s") % str(e),
                subject=_("QR Code Error"),
            )
            raise UserError(_("Failed to get QR code: %s") % str(e))

    def action_refresh_status(self):
        """Refresh session status"""
        self.ensure_one()

        session_id = self.id
        waha_session_id = self.session_id
        _logger.debug(f"Refreshing status for session id={session_id}")

        try:
            status_data = self._make_api_request(f'sessions/{waha_session_id}')

            if status_data:
                old_status = self.status
                new_status = status_data.get('status', 'stopped').lower()

                me_data = status_data.get('me') or {}
                new_phone = me_data.get('id', '').replace('@c.us', '') if me_data else ''
                old_phone = self.phone_number

                self.status = new_status
                if me_data:
                    self.phone_number = new_phone
                    self.profile_name = me_data.get('pushName', '')
                self.last_sync = fields.Datetime.now()
                self.error_message = False

                # Log profile update
                if me_data and old_phone != new_phone and new_phone:
                    _logger.info(f"Session id={session_id} authenticated with phone: {new_phone}")
                    self.message_post(
                        body=_("Session authenticated successfully!<br/>Phone: %s<br/>Profile: %s") % (
                            new_phone, me_data.get('pushName', '') or 'N/A'
                        ),
                        subject=_("Session Authenticated")
                    )

                # Log status changes
                if old_status != new_status:
                    _logger.info(f"Session id={session_id} status changed: {old_status} → {new_status}")
                    if new_status == 'working':
                        self.message_post(
                            body=_("Session is now working and ready to send/receive messages."),
                            subject=_("Session Active")
                        )
                    elif new_status == 'scan_qr_code':
                        self.message_post(
                            body=_("Session is waiting for QR code scan."),
                            subject=_("Scan Required")
                        )
                    elif new_status == 'failed':
                        self.message_post(
                            body=_("Session has failed. Please check logs and restart."),
                            subject=_("Session Failed")
                        )

        except Exception as e:
            self.error_message = str(e)
            _logger.error(f"Failed to refresh status for session id={session_id}: {e}")

    def check_connection_status(self):
        """Refresh from WAHA and return the current status string. Used by the
        QR widget to poll for connection during pairing (works even when
        webhooks are not reachable)."""
        self.ensure_one()
        self.action_refresh_status()
        return self.status

    def resolve_lid_to_chat_id(self, chat_id):
        """If chat_id ends with @lid, resolve it to a real @c.us chat ID via WAHA LID API.
        Returns the resolved chat_id, or the original if resolution fails.
        """
        if not chat_id or '@lid' not in chat_id:
            return chat_id
        try:
            lid_encoded = chat_id.replace('@', '%40')
            data = self._make_api_request(f'{self.session_id}/lids/{lid_encoded}', 'GET')
            pn = data.get('pn', '') if isinstance(data, dict) else ''
            if pn:
                resolved = pn if '@' in pn else f"{pn}@c.us"
                _logger.info(f"Resolved LID {chat_id} -> {resolved}")
                return resolved
        except Exception as e:
            _logger.debug(f"Could not resolve LID {chat_id}: {e}")
        return chat_id

    def fetch_chat_messages_from_api(self, chat_id, limit=50, offset=0):
        """Fetch messages directly from WAHA API for a given chat.
        Raises on failure so the caller can decide to fall back.
        WAHA returns messages newest-first.
        """
        self.ensure_one()
        resolved_id = self.resolve_lid_to_chat_id(chat_id)
        params = {'limit': limit, 'offset': offset}
        result = self._make_api_request(
            f'{self.session_id}/chats/{resolved_id}/messages',
            'GET',
            params=params,
        )
        return result if isinstance(result, list) else []

    def send_message(self, chat_id, text, file_data=None, file_name=None, file_type=None):
        """Send message through WhatsApp"""
        self.ensure_one()

        if self.status != 'working':
            _logger.warning(f"Attempted to send message on inactive session {self.name} (status: {self.status})")
            raise UserError(_("Session is not active. Current status: %s") % self.status)

        _logger.info(f"Sending message from session {self.name} to {chat_id}")

        try:
            if file_data:
                # Send file message
                endpoint = 'sendImage' if file_type and file_type.startswith('image/') else 'sendFile'

                data = {
                    'chatId': chat_id,
                    'session': self.session_id,
                    'file': {
                        'mimetype': file_type or 'application/octet-stream',
                        'filename': file_name or 'file',
                        'data': file_data
                    }
                }

                if text:
                    data['caption'] = text

                _logger.info(f"Sending file message: {file_name} to {chat_id}")

            else:
                # Send text message
                endpoint = 'sendText'
                data = {
                    'chatId': chat_id,
                    'text': text,
                    'session': self.session_id
                }

            result = self._make_api_request(endpoint, 'POST', data)

            _logger.info(f"Message sent successfully from {self.name} to {chat_id}")

            return result

        except Exception as e:
            _logger.error(f"Failed to send message from session {self.name}: {e}")
            raise UserError(_("Failed to send message: %s") % str(e))

    @staticmethod
    def phone_to_chat_id(phone):
        """Normalise a raw phone number into a WhatsApp chat id.
        Returns '' when no digits are present."""
        import re as _re
        digits = _re.sub(r'\D', '', phone or '')
        if not digits:
            return ''
        return '%s@c.us' % digits

    def create_and_send(self, text, partner=None, phone=None, chat_id=None,
                        attachment=None, message_type='text', res_model=None,
                        res_id=None, campaign_recipient=None, log_on_record=True):
        """Create an outgoing message record and dispatch it through WAHA.

        Central send path shared by campaigns, automation rules and
        auto-replies. Returns the created ``waha.whatsapp.message``.
        The message status reflects the send outcome ('sent' or 'failed').
        """
        self.ensure_one()
        if partner is None and phone is None and chat_id is None:
            raise UserError(_("A partner, phone number or chat id is required to send a message."))

        if not phone and partner:
            phone = partner.waha_whatsapp_number or getattr(partner, 'mobile', '') or partner.phone or ''
        if not chat_id:
            chat_id = partner.waha_chat_id() if partner else self.phone_to_chat_id(phone)
        if not chat_id:
            raise UserError(_("No valid WhatsApp number for %s.") % (partner.display_name if partner else phone))

        vals = {
            'session_id': self.id,
            'partner_id': partner.id if partner else False,
            'phone_number': phone or chat_id.split('@')[0],
            'chat_id': chat_id,
            'text': text or '',
            'direction': 'outgoing',
            'message_type': message_type,
            'status': 'draft',
        }
        if attachment:
            vals['attachment_id'] = attachment.id
            if message_type == 'text':
                mt = attachment.mimetype or ''
                if mt.startswith('image/'):
                    vals['message_type'] = 'image'
                elif mt.startswith('video/'):
                    vals['message_type'] = 'video'
                elif mt.startswith('audio/'):
                    vals['message_type'] = 'voice'
                else:
                    vals['message_type'] = 'document'
        if res_model and res_id:
            vals['res_model'] = res_model
            vals['res_id'] = res_id
        if campaign_recipient:
            vals['campaign_recipient_id'] = campaign_recipient.id
            vals['campaign_id'] = campaign_recipient.campaign_id.id

        message = self.env['waha.whatsapp.message'].create(vals)
        message.action_send()
        if log_on_record:
            message._log_on_related_record()
        return message

    def send_voice_message(self, chat_id, voice_data, voice_filename='voice.ogg'):
        """Send voice message"""
        self.ensure_one()

        _logger.info(f"Sending voice message from session {self.name} to {chat_id}")

        try:
            data = {
                'chatId': chat_id,
                'session': self.session_id,
                'file': {
                    'mimetype': 'audio/ogg',
                    'filename': voice_filename,
                    'data': voice_data
                }
            }

            result = self._make_api_request('sendVoice', 'POST', data)

            _logger.info(f"Voice message sent successfully from {self.name} to {chat_id}")

            return result

        except Exception as e:
            _logger.error(f"Failed to send voice message from session {self.name}: {e}")
            raise UserError(_("Failed to send voice message: %s") % str(e))

    def send_seen(self, chat_id, message_ids, participant=None):
        """Mark messages as seen via WAHA /api/sendSeen"""
        self.ensure_one()
        data = {
            'chatId': chat_id,
            'session': self.session_id,
            'messageIds': message_ids,
            'participant': participant,
        }
        return self._make_api_request('sendSeen', 'POST', data)

    def start_typing(self, chat_id):
        """Send typing indicator via WAHA /api/startTyping"""
        self.ensure_one()
        data = {'chatId': chat_id, 'session': self.session_id}
        return self._make_api_request('startTyping', 'POST', data)

    def stop_typing(self, chat_id):
        """Send stop-typing indicator via WAHA /api/stopTyping"""
        self.ensure_one()
        data = {'chatId': chat_id, 'session': self.session_id}
        return self._make_api_request('stopTyping', 'POST', data)

    def action_view_messages(self):
        """View all messages for this session"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'WhatsApp Messages',
            'res_model': 'waha.whatsapp.message',
            'view_mode': 'list,form',
            'domain': [('session_id', '=', self.id)],
            'context': {'default_session_id': self.id}
        }

    def action_view_sent_messages(self):
        """View outgoing messages for this session"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sent Messages',
            'res_model': 'waha.whatsapp.message',
            'view_mode': 'list,form',
            'domain': [('session_id', '=', self.id), ('direction', '=', 'outgoing')],
            'context': {'default_session_id': self.id, 'default_direction': 'outgoing'}
        }

    def action_view_received_messages(self):
        """View incoming messages for this session"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Received Messages',
            'res_model': 'waha.whatsapp.message',
            'view_mode': 'list,form',
            'domain': [('session_id', '=', self.id), ('direction', '=', 'incoming')],
            'context': {'default_session_id': self.id, 'default_direction': 'incoming'}
        }

    def action_update_webhook(self):
        """Register our webhook exactly once, removing any duplicate copies of
        the same URL (webhooks for other URLs are preserved).

        WAHA delivers every message once per registered webhook, so duplicate
        registrations of our URL cause auto-replies / inbound handlers to fire
        multiple times. This method is idempotent and also cleans up any
        duplicates a previous 'append' behaviour may have accumulated."""
        self.ensure_one()

        session_id = self.id
        _logger.info(f"Updating webhook configuration for session id={session_id}")

        if not self.webhook_url:
            raise UserError(_("No webhook URL configured."))

        self.env.cr.flush()

        webhook_url = self.webhook_url
        webhook_events = self.webhook_events
        waha_session_id = self.session_id
        events = [e.strip() for e in webhook_events.split(',')] if webhook_events else ['message']

        # Fetch existing session config to preserve webhooks for OTHER urls.
        existing_webhooks = []
        try:
            session_info = self._make_api_request(f'sessions/{waha_session_id}', 'GET')
            existing_webhooks = (session_info or {}).get('config', {}).get('webhooks', [])
        except Exception as e:
            _logger.debug(f"Could not fetch existing webhooks for session id={session_id}: {e}")

        # Drop every existing entry pointing at our URL, then add a single fresh
        # one — so our webhook is registered exactly once.
        removed = len(existing_webhooks)
        webhooks = [w for w in existing_webhooks
                    if isinstance(w, dict) and w.get('url') != webhook_url]
        removed -= len(webhooks)
        webhooks.append({'url': webhook_url, 'events': events})
        if removed:
            _logger.info("Removed %s duplicate webhook registration(s) for %s", removed, webhook_url)

        self._make_api_request(f'sessions/{waha_session_id}', 'PUT', {
            'name': waha_session_id,
            'config': {
                'noweb': {'store': {'enabled': True, 'full_sync': True}},
                'webhooks': webhooks,
            }
        })

        _logger.info(f"Webhook updated successfully for session id={session_id}: {webhook_url}")

        # Avoid writing to the session record here — concurrent webhook
        # transactions update the same row and cause SerializationFailure.
        # The success notification below is sufficient feedback to the user.

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Webhook configuration updated successfully!'),
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def _get_default_webhook_url(self):
        """Get default webhook URL based on Odoo base URL"""
        try:
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            if base_url:
                base_url = base_url.rstrip('/')
                return f"{base_url}/waha/whatsapp/webhook"
            else:
                return "http://localhost:8069/waha/whatsapp/webhook"
        except:
            return "http://localhost:8069/waha/whatsapp/webhook"

    def action_set_default_webhook(self):
        """Set default webhook URL automatically"""
        self.ensure_one()

        default_webhook = self._get_default_webhook_url()
        self.webhook_url = default_webhook

        _logger.info(f"Default webhook URL set for session {self.name}: {default_webhook}")

        self.message_post(
            body=_("Default webhook URL has been set: %s") % default_webhook,
            subject=_("Webhook Configured")
        )

        # حفظ التغييرات صراحة
        self.env.cr.commit()

        return {
            'type': 'ir.actions.act_window',
            'name': _('WhatsApp Session'),
            'res_model': 'waha.whatsapp.session',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'show_notification': True,
                'notification_message': _('Default webhook URL set: %s') % default_webhook
            }
        }

    def action_auto_configure_webhook(self):
        """Auto configure webhook with default settings"""
        self.ensure_one()

        session_id = self.id
        _logger.info(f"Auto-configuring webhook for session id={session_id}")

        self.webhook_url = self._get_default_webhook_url()

        if not self.webhook_events:
            self.webhook_events = 'message.any,message.ack,session.status'

        self.env.cr.flush()

        if self.status in ['working', 'scan_qr_code']:
            try:
                self.action_update_webhook()
                message = _('Webhook auto-configured and updated successfully!')
            except Exception as e:
                _logger.warning(f"Auto-configure webhook update failed for session id={session_id}: {e}")
                message = _('Webhook URL set. Please update webhook manually.')
        else:
            message = _('Webhook URL configured. Will be applied when session starts.')

            self.message_post(
                body=_("Webhook auto-configured.<br/>URL: %s<br/>Events: %s") % (
                    self.webhook_url, self.webhook_events
                ),
                subject=_("Auto Configuration")
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def default_get(self, fields_list):
        """Set default values including webhook URL"""
        res = super().default_get(fields_list)

        if 'webhook_url' in fields_list and not res.get('webhook_url'):
            res['webhook_url'] = self._get_default_webhook_url()

        if 'webhook_events' in fields_list and not res.get('webhook_events'):
            res['webhook_events'] = 'message.any,message.ack,session.status'

        return res

    # ==================================================================
    # Full sync from the phone (contacts + chat history)
    # ==================================================================
    _MSG_TYPE_MAP = {
        'chat': 'text', 'text': 'text', 'image': 'image', 'ptt': 'voice',
        'audio': 'audio', 'voice': 'voice', 'video': 'video', 'document': 'document',
        'sticker': 'sticker', 'location': 'location', 'vcard': 'document',
        'multi_vcard': 'document', 'notification_template': 'notification',
        'e2e_notification': 'notification', 'gp2': 'notification', 'call_log': 'notification',
    }

    @staticmethod
    def _sync_sanitize(raw):
        """Digits-only phone with basic E.164 sanity (7-15 digits), else ''."""
        if not raw:
            return ''
        for suffix in ('@c.us', '@s.whatsapp.net', '@lid', '@g.us', '@broadcast'):
            raw = raw.replace(suffix, '')
        digits = ''.join(c for c in raw if c.isdigit())
        if len(digits) < 7 or len(digits) > 15:
            return ''
        return digits

    def _normalize_msg_type(self, waha_type):
        return self._MSG_TYPE_MAP.get((waha_type or '').lower(), 'chat')

    @api.model
    def _get_waha_import_tag(self):
        """Return (creating if needed) the 'WhatsApp' contact tag used to mark
        partners created by a phone sync."""
        Category = self.env['res.partner.category'].sudo()
        tag = Category.search([('name', '=', 'WhatsApp')], limit=1)
        if not tag:
            tag = Category.create({'name': 'WhatsApp', 'color': 2})
        return tag

    def _find_partner_by_phone(self, phone):
        """Look up a res.partner by a digits-only phone number."""
        if not phone:
            return self.env['res.partner']
        mobile = phone if phone.startswith('+') else '+' + phone
        Partner = self.env['res.partner'].sudo()
        # 'mobile' was removed from res.partner in Odoo 19 — only match it where it exists.
        terms = [('phone_sanitized', '=', mobile), ('phone', 'in', (mobile, phone))]
        if 'mobile' in Partner._fields:
            terms.append(('mobile', 'in', (mobile, phone)))
        domain = ['|'] * (len(terms) - 1) + terms
        return Partner.search(domain, limit=1)

    def sync_contacts(self, only_named=True, update_names=False):
        """Import the phone's contact book into res.partner.
        Returns a {created, updated, skipped} summary. Idempotent.

        When ``update_names`` is set, an existing contact's name is refreshed
        from the phone's saved name — but only if it was not manually edited in
        Odoo (i.e. the current name still equals the phone name we stored last
        sync in ``waha_synced_name``). Hand-edited names are always preserved."""
        self.ensure_one()
        Partner = self.env['res.partner'].sudo()
        tag = self._get_waha_import_tag()
        created = updated = skipped = 0
        offset, page, seen = 0, 500, 0

        while True:
            batch = self._make_api_request(
                'contacts/all', 'GET',
                params={'session': self.session_id, 'limit': page, 'offset': offset},
            )
            if not isinstance(batch, list) or not batch:
                break

            for c in batch:
                if c.get('isGroup') or c.get('isMe'):
                    skipped += 1
                    continue
                cid = c.get('id') or ''
                if '@g.us' in cid:
                    skipped += 1
                    continue
                phone = self._sync_sanitize(c.get('number') or cid)
                if not phone:
                    skipped += 1
                    continue
                saved_name = c.get('name')
                if only_named and not saved_name:
                    skipped += 1
                    continue
                name = saved_name or c.get('pushname') or c.get('shortName') or ('+' + phone)
                partner = self._find_partner_by_phone(phone)
                if partner:
                    vals = {}
                    if tag not in partner.category_id:
                        vals['category_id'] = [(4, tag.id)]
                    if update_names and saved_name:
                        # Overwrite the name only when it still matches the phone
                        # name we recorded last time (= not edited in Odoo).
                        if (partner.name == (partner.waha_synced_name or '')
                                and partner.name != saved_name):
                            vals['name'] = saved_name
                        # Track the phone's current saved name either way.
                        if partner.waha_synced_name != saved_name:
                            vals['waha_synced_name'] = saved_name
                    if vals:
                        partner.write(vals)
                    updated += 1
                else:
                    # Odoo 19 dropped res.partner.mobile — store the number in
                    # 'mobile' where it exists, otherwise in 'phone'.
                    number_field = 'mobile' if 'mobile' in Partner._fields else 'phone'
                    Partner.create({
                        'name': name,
                        number_field: '+' + phone,
                        'is_company': False,
                        'category_id': [(4, tag.id)],
                        'waha_synced_name': saved_name or name,
                    })
                    created += 1

            seen += len(batch)
            offset += len(batch)
            self.env.cr.commit()
            if len(batch) < page or seen > 20000:
                break

        self.last_sync_contacts = fields.Datetime.now()
        _logger.info("Contacts sync for %s: created=%s updated=%s skipped=%s",
                     self.name, created, updated, skipped)
        return {'created': created, 'updated': updated, 'skipped': skipped}

    def _import_history_message(self, chat_id, m, partner, phone):
        """Store one historical WAHA message. Returns 'created' or 'skipped'."""
        raw_id = m.get('id')
        if isinstance(raw_id, dict):
            wid = raw_id.get('_serialized') or raw_id.get('id') or ''
        else:
            wid = str(raw_id or '')
        if not wid:
            return 'skipped'

        Message = self.env['waha.whatsapp.message'].sudo()
        if Message.search_count([('waha_message_id', '=', wid)]):
            return 'skipped'

        ack = m.get('ack') or 0
        status = 'read' if ack >= 3 else 'delivered' if ack >= 2 else 'sent'
        msg = Message.create({
            'session_id': self.id,
            'partner_id': partner.id if partner else False,
            'phone_number': phone or (chat_id or '').split('@')[0],
            'chat_id': chat_id,
            'text': m.get('body') or '',
            'direction': 'outgoing' if m.get('fromMe') else 'incoming',
            'message_type': self._normalize_msg_type(m.get('type')),
            'status': status,
            'waha_message_id': wid,
        })
        # Backdate to the real WhatsApp time so history keeps its chronology
        # (the dedup create() path stamps create_date=now()).
        ts = m.get('timestamp')
        if ts and msg:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
            self.env.cr.execute(
                "UPDATE waha_whatsapp_message SET create_date = %s WHERE id = %s",
                (dt, msg.id),
            )
        return 'created' if msg else 'skipped'

    def _collect_chat_ids(self, include_groups=False):
        """Return the ordered, de-duplicated list of chat ids to sync."""
        self.ensure_one()
        seen, out = set(), []
        offset, page = 0, 50
        while True:
            chats = self._make_api_request(
                '%s/chats/overview' % self.session_id, 'GET',
                params={'limit': page, 'offset': offset},
            )
            if not isinstance(chats, list) or not chats:
                break
            for ch in chats:
                cid = ch.get('id') or ''
                if not cid or cid in seen:
                    continue
                if '@g.us' in cid and not include_groups:
                    continue
                seen.add(cid)
                out.append(cid)
            offset += len(chats)
            if len(chats) < page:
                break
        return out

    def _sync_chat_messages(self, chat_id, message_limit=100):
        """Import one chat's recent messages + refresh its conversation.
        Returns (imported, skipped)."""
        self.ensure_one()
        is_group = '@g.us' in (chat_id or '')
        phone = '' if is_group else self._sync_sanitize((chat_id or '').split('@')[0])
        partner = self._find_partner_by_phone(phone) if phone else self.env['res.partner']
        self.env['waha.whatsapp.chat.thread'].sudo()._get_or_create(
            self, chat_id, partner or None, phone)
        try:
            msgs = self.fetch_chat_messages_from_api(chat_id, limit=message_limit)
        except Exception as e:  # noqa: BLE001
            _logger.warning("Could not fetch messages for chat %s: %s", chat_id, e)
            msgs = []
        imported = skipped = 0
        for m in msgs:
            if self._import_history_message(chat_id, m, partner, phone) == 'created':
                imported += 1
            else:
                skipped += 1
        return imported, skipped

    def sync_messages(self, message_limit=100, include_groups=False):
        """Import chat history for every chat into the message log + inbox
        synchronously. Returns a {chats, imported, skipped} summary. Idempotent."""
        self.ensure_one()
        imported = skipped = 0
        chat_ids = self._collect_chat_ids(include_groups=include_groups)
        for chat_id in chat_ids:
            i, s = self._sync_chat_messages(chat_id, message_limit=message_limit)
            imported += i
            skipped += s
            self.env.cr.commit()
        self.last_sync_messages = fields.Datetime.now()
        _logger.info("Messages sync for %s: chats=%s imported=%s skipped=%s",
                     self.name, len(chat_ids), imported, skipped)
        return {'chats': len(chat_ids), 'imported': imported, 'skipped': skipped}

    def action_open_sync_wizard(self):
        """Open the 'Sync from Phone' wizard for this session."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sync from Phone'),
            'res_model': 'waha.whatsapp.sync.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_session_id': self.id},
        }

    @api.model
    def cron_refresh_all_sessions(self):
        """Cron job to refresh all active sessions"""
        _logger.info("Starting cron job: Refresh all active WhatsApp sessions")

        active_sessions = self.search([('active', '=', True)])

        _logger.info(f"Found {len(active_sessions)} active sessions to refresh")

        success_count = 0
        error_count = 0

        for session in active_sessions:
            try:
                session.action_refresh_status()
                success_count += 1
            except Exception as e:
                error_count += 1
                _logger.error(f"Failed to refresh session {session.name}: {e}")

        _logger.info(f"Cron job completed: {success_count} successful, {error_count} failed")