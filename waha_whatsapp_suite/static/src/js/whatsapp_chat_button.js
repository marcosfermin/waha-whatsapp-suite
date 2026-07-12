/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { WhatsappChatDialog } from "./whatsapp_chat_dialog";

// Helper: extract id and display_name from a Many2one value.
// Odoo 17: [id, display_name] array
// Odoo 18/19: {id, display_name} object
function m2oId(val) {
    if (!val) return false;
    if (Array.isArray(val)) return val[0];
    if (typeof val === 'object') return val.id;
    return val;
}
function m2oName(val) {
    if (!val) return '';
    if (Array.isArray(val)) return val[1] || '';
    if (typeof val === 'object') return val.display_name || '';
    return '';
}

export class WhatsappChatButton extends Component {
    static template = "waha_whatsapp_suite.WhatsappChatButton";
    static props = ["record", "readonly", "class"];

    setup() {}

    openChat() {
        const record = this.props.record.data;
        const sessionId = m2oId(record.session_id);
        const partnerId = m2oId(record.partner_id) || false;
        const partnerName = m2oName(record.partner_id) || record.phone_number;

        const remove = this.env.services.overlay.add(WhatsappChatDialog, {
            chatId: record.chat_id,
            sessionId: sessionId,
            phoneNumber: record.phone_number,
            partnerId: partnerId || false,
            partnerName: partnerName || record.phone_number,
            close: () => remove(),
        });
    }
}

registry.category("view_widgets").add("whatsapp_chat_button", {
    component: WhatsappChatButton,
});
