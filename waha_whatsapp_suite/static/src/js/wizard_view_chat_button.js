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

export class WizardViewChatButton extends Component {
    static template = "waha_whatsapp_suite.WizardViewChatButton";
    static props = ["record", "readonly", "class?"];

    openChat() {
        const data = this.props.record.data;
        const sessionId = m2oId(data.session_id);
        const partnerId = m2oId(data.partner_id) || false;
        const partnerName = m2oName(data.partner_id) || data.phone_number;

        if (!sessionId) {
            this.env.services.notification.add("Please select a WhatsApp session first", { type: "warning" });
            return;
        }
        if (!data.phone_number) {
            this.env.services.notification.add("Please enter a phone number first", { type: "warning" });
            return;
        }

        let phone = (data.phone_number || "").trim().replace(/^\+/, "").replace(/\D/g, "");
        const chatId = `${phone}@c.us`;

        const remove = this.env.services.overlay.add(WhatsappChatDialog, {
            chatId: chatId,
            sessionId: sessionId,
            phoneNumber: data.phone_number,
            partnerId: partnerId || false,
            partnerName: partnerName || data.phone_number,
            close: () => remove(),
        });
    }
}

registry.category("view_widgets").add("wizard_view_chat_button", {
    component: WizardViewChatButton,
});
