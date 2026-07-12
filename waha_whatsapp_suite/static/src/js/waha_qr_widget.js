/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillUnmount } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

/**
 * Renders the live WhatsApp pairing QR code for a session, refreshing it on an
 * interval (the QR rotates every ~20s) and switching to a success state once
 * the session reports "working". The image is served by Odoo's authenticated
 * /waha/session/qr proxy, so the browser never talks to WAHA directly.
 */
export class WahaQrCode extends Component {
    static template = "waha_whatsapp_suite.WahaQrCode";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            ts: new Date().getTime(),
            connected: false,
            imgReady: false,
        });
        // Poll status + rotate the QR every 12s.
        this.timer = setInterval(() => this._tick(), 12000);
        onWillUnmount(() => clearInterval(this.timer));
    }

    get sessionId() {
        return this.props.record.resId;
    }

    get src() {
        if (!this.sessionId) {
            return "";
        }
        return `/waha/session/qr?session_id=${this.sessionId}&t=${this.state.ts}`;
    }

    async _tick() {
        const id = this.sessionId;
        if (!id) {
            return;
        }
        try {
            // Live status check against WAHA so we detect the connection even
            // without webhooks configured.
            const status = await this.orm.call(
                "waha.whatsapp.session", "check_connection_status", [[id]]
            );
            if (status === "working") {
                this.state.connected = true;
                clearInterval(this.timer);
                return;
            }
        } catch (e) {
            // Ignore transient errors; keep trying.
        }
        // Force the <img> to reload with a fresh QR.
        this.state.ts = new Date().getTime();
    }

    onImgLoad() {
        this.state.imgReady = true;
    }

    onImgError() {
        this.state.imgReady = false;
    }
}

export const wahaQrCode = {
    component: WahaQrCode,
    supportedTypes: ["binary"],
};

registry.category("fields").add("waha_qr_code", wahaQrCode);
