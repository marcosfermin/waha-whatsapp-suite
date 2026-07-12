/** @odoo-module **/

/**
 * Odoo 17.0: Thread.prototype.open() does not exist — open() and
 * markAllMessagesAsRead() live on ThreadService ("mail.thread").
 * We only register the client action component triggered by
 * get_formview_action() on waha.whatsapp.message.
 */

import { registry } from "@web/core/registry";
import { Component, xml } from "@odoo/owl";
import { WhatsappChatDialog } from "./whatsapp_chat_dialog";
import { useService } from "@web/core/utils/hooks";

class OpenWhatsappChat extends Component {
    static template = xml`<div/>`;
    static props = ["*"];

    setup() {
        const overlay = useService("overlay");
        const p = this.props.action.params || {};
        const remove = overlay.add(WhatsappChatDialog, {
            chatId: p.chat_id,
            sessionId: p.session_id,
            phoneNumber: p.phone_number,
            partnerId: p.partner_id || false,
            partnerName: p.partner_name || p.phone_number,
            close: () => remove(),
        });
    }
}

registry.category("actions").add("waha_whatsapp_open_chat", OpenWhatsappChat);
