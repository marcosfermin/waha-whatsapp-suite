# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import json
import logging

_logger = logging.getLogger(__name__)


class WahaWhatsappSyncJob(models.Model):
    """A resumable, cron-driven 'Sync from Phone' job. The cron processes a
    bounded number of chats per run so large histories import in the background
    without blocking a web worker."""
    _name = 'waha.whatsapp.sync.job'
    _description = 'WhatsApp Sync Job'
    _order = 'create_date desc'
    _rec_name = 'display_name'

    session_id = fields.Many2one('waha.whatsapp.session', 'Session', required=True,
                                 ondelete='cascade', index=True)
    display_name = fields.Char(compute='_compute_display_name')

    sync_contacts = fields.Boolean('Sync Contacts', default=True)
    only_named_contacts = fields.Boolean('Only saved contacts', default=True)
    update_contact_names = fields.Boolean('Update names from phone', default=False)
    sync_messages = fields.Boolean('Sync Messages', default=True)
    message_limit = fields.Integer('Messages / chat', default=100)
    include_groups = fields.Boolean('Include groups', default=False)
    chats_per_run = fields.Integer('Chats per run', default=10,
                                   help="How many chats the cron imports each time it runs.")

    state = fields.Selection([
        ('queued', 'Queued'),
        ('collecting', 'Collecting Chats'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], default='queued', required=True, index=True)

    chat_ids_json = fields.Text('Chat IDs', readonly=True)
    total_chats = fields.Integer('Total Chats', readonly=True)
    cursor = fields.Integer('Processed Chats', readonly=True)
    progress = fields.Float('Progress %', compute='_compute_progress')

    contacts_done = fields.Boolean(readonly=True)
    contacts_created = fields.Integer('Contacts Created', readonly=True)
    contacts_updated = fields.Integer('Contacts Updated', readonly=True)
    contacts_skipped = fields.Integer('Contacts Skipped', readonly=True)
    imported_messages = fields.Integer('Messages Imported', readonly=True)
    skipped_messages = fields.Integer('Messages Skipped', readonly=True)
    error = fields.Text('Error', readonly=True)
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company)

    @api.depends('session_id', 'state')
    def _compute_display_name(self):
        for job in self:
            job.display_name = _("Sync %s (%s)") % (
                job.session_id.name or '', dict(self._fields['state'].selection).get(job.state, ''))

    @api.depends('cursor', 'total_chats')
    def _compute_progress(self):
        for job in self:
            job.progress = (100.0 * job.cursor / job.total_chats) if job.total_chats else 0.0

    # ------------------------------------------------------------------
    def action_cancel(self):
        self.filtered(lambda j: j.state in ('queued', 'collecting', 'running')).write(
            {'state': 'cancelled'})

    def action_requeue(self):
        for job in self:
            job.write({
                'state': 'queued',
                'cursor': 0,
                'chat_ids_json': False,
                'total_chats': 0,
                'contacts_done': False,
                'imported_messages': 0,
                'skipped_messages': 0,
                'error': False,
            })

    # ------------------------------------------------------------------
    def _process_tick(self):
        """Advance this job by one bounded step. Commits its own progress."""
        self.ensure_one()
        session = self.session_id
        if not session or session.status != 'working':
            # Not connected yet — leave the job queued and try again next tick.
            return

        if self.state == 'queued':
            if self.sync_contacts and not self.contacts_done:
                res = session.sync_contacts(only_named=self.only_named_contacts,
                                            update_names=self.update_contact_names)
                self.write({
                    'contacts_done': True,
                    'contacts_created': res['created'],
                    'contacts_updated': res['updated'],
                    'contacts_skipped': res['skipped'],
                })
                self.env.cr.commit()
            if not self.sync_messages:
                self.write({'state': 'done'})
                self.env.cr.commit()
                return
            self.write({'state': 'collecting'})
            self.env.cr.commit()
            return

        if self.state == 'collecting':
            chat_ids = session._collect_chat_ids(include_groups=self.include_groups)
            self.write({
                'chat_ids_json': json.dumps(chat_ids),
                'total_chats': len(chat_ids),
                'cursor': 0,
                'state': 'running' if chat_ids else 'done',
            })
            if not chat_ids:
                session.last_sync_messages = fields.Datetime.now()
            self.env.cr.commit()
            return

        if self.state == 'running':
            chat_ids = json.loads(self.chat_ids_json or '[]')
            start = self.cursor
            end = min(start + max(1, self.chats_per_run), len(chat_ids))
            for idx in range(start, end):
                chat_id = chat_ids[idx]
                try:
                    i, s = session._sync_chat_messages(chat_id, message_limit=self.message_limit)
                except Exception as e:  # noqa: BLE001
                    _logger.warning("Sync job %s: chat %s failed: %s", self.id, chat_id, e)
                    i, s = 0, 0
                self.write({
                    'cursor': idx + 1,
                    'imported_messages': self.imported_messages + i,
                    'skipped_messages': self.skipped_messages + s,
                })
                self.env.cr.commit()
            if self.cursor >= self.total_chats:
                self.write({'state': 'done'})
                session.last_sync_messages = fields.Datetime.now()
                self.env.cr.commit()
            return

    @api.model
    def cron_process_sync_jobs(self):
        """Process one active sync job per run (bounded by chats_per_run)."""
        job = self.search(
            [('state', 'in', ['queued', 'collecting', 'running'])],
            order='create_date', limit=1,
        )
        if not job:
            return
        try:
            job._process_tick()
        except Exception as e:  # noqa: BLE001
            _logger.exception("WhatsApp sync job %s failed", job.id)
            self.env.cr.rollback()
            job.write({'state': 'failed', 'error': str(e)})
            self.env.cr.commit()
