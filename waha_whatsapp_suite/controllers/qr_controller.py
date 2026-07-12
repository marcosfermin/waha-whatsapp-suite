from odoo import http
from odoo.http import request, Response
import logging

_logger = logging.getLogger(__name__)


class WahaQrController(http.Controller):
    """Serve the live pairing QR image through Odoo so the QR can be scanned
    from the session form without opening the WAHA dashboard — and without ever
    exposing the WAHA URL or API key to the browser."""

    @http.route('/waha/session/qr', type='http', auth='user', methods=['GET'], csrf=False)
    def session_qr(self, session_id=None, **kw):
        if not session_id:
            return request.not_found()
        try:
            session = request.env['waha.whatsapp.session'].browse(int(session_id))
            # Enforce the caller's own access rights before using sudo to fetch.
            session.check_access_rights('read')
            session.check_access_rule('read')
        except Exception:
            return request.not_found()

        try:
            content = session.sudo()._fetch_qr_image()
        except Exception as e:  # noqa: BLE001
            _logger.debug("Live QR fetch failed for session %s: %s", session_id, e)
            content = None

        if not content:
            # No QR available yet (still starting) or already connected.
            return Response(status=204)

        return Response(content, status=200, headers={
            'Content-Type': 'image/png',
            'Cache-Control': 'no-store, max-age=0',
        })
