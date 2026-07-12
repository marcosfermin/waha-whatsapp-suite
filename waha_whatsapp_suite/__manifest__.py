{
    'name': 'WhatsApp Suite (WAHA)',
    'version': '18.0.1.0.0',
    'category': 'Marketing',
    'summary': 'WhatsApp for Odoo via WAHA: chat, campaigns, automation, shared inbox, CRM/Helpdesk',
    'description': '''
        WhatsApp Suite for Odoo (WAHA)
        ==============================

        A complete WhatsApp toolkit for Odoo built on the WAHA (WhatsApp HTTP API)
        engine: live chat, in-Odoo QR pairing, marketing campaigns, automation,
        auto-replies, a shared inbox, phone sync, and CRM / Sales / Project /
        Helpdesk integration.

        Features:
        - Manage WhatsApp sessions with QR code scanning
        - Send text messages, files, and voice messages
        - Set default WhatsApp account per company
        - WhatsApp message templates with variables
        - Template variables auto-fill from record data
        - Integration with Odoo contacts and partners
        - Bulk messaging campaigns with throttling, scheduling and opt-out
        - Automation rules: "Send WhatsApp" server action on any Odoo event
        - Inbound keyword auto-replies / chatbot rules
        - Shared-inbox conversations (assignment + status) and canned replies
        - CRM / Sales / Project / Helpdesk linking and analytics dashboards
    ''',
    'author': 'Marcos Fermin',
    'website': 'https://www.marcosfermin.com',
    'depends': ['base', 'mail', 'contacts', 'base_automation', 'crm', 'sale', 'project'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'data/waha_automation_data.xml',
        'views/waha_session_views.xml',
        'views/waha_session_chat_views.xml',
        'views/res_company_views.xml',
        'views/whatsapp_message_views.xml',
        'views/whatsapp_template_views.xml',
        'views/whatsapp_template_variable_views.xml',
        'views/res_partner_views.xml',
        'views/waha_campaign_views.xml',
        'views/waha_autoreply_views.xml',
        'views/waha_canned_reply_views.xml',
        'views/waha_chat_thread_views.xml',
        'views/waha_sync_job_views.xml',
        'views/ir_actions_server_views.xml',
        'views/whatsapp_report_views.xml',
        'views/crm_lead_views.xml',
        'views/sale_order_views.xml',
        'views/project_task_views.xml',
        'wizard/send_whatsapp_wizard_views.xml',
        'wizard/add_to_campaign_wizard_views.xml',
        'wizard/sync_wizard_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'waha_whatsapp_suite/static/src/css/waha_style.css',
            'waha_whatsapp_suite/static/src/js/waha_qr_widget.js',
            'waha_whatsapp_suite/static/src/xml/waha_qr_widget.xml',
            'waha_whatsapp_suite/static/src/js/chatter_whatsapp_button.js',
            'waha_whatsapp_suite/static/src/xml/chatter_whatsapp_button.xml',
            'waha_whatsapp_suite/static/src/js/whatsapp_chat_dialog.js',
            'waha_whatsapp_suite/static/src/js/whatsapp_chat_button.js',
            'waha_whatsapp_suite/static/src/js/wizard_view_chat_button.js',
            'waha_whatsapp_suite/static/src/js/whatsapp_message_open_chat.js',
            'waha_whatsapp_suite/static/src/xml/whatsapp_chat_dialog.xml',
            'waha_whatsapp_suite/static/src/xml/whatsapp_chat_button.xml',
            'waha_whatsapp_suite/static/src/xml/wizard_view_chat_button.xml',
            # WhatsApp-Web-style live chat UI (merged from waha_whatsapp_chat)
            'waha_whatsapp_suite/static/src/js/waha_chat_action.js',
            'waha_whatsapp_suite/static/src/js/waha_float.js',
            'waha_whatsapp_suite/static/src/xml/waha_chat_action.xml',
            'waha_whatsapp_suite/static/src/xml/waha_float.xml',
            'waha_whatsapp_suite/static/src/css/waha_chat.css',
        ],
    },
    'support': 'https://www.marcosfermin.com',
    'installable': True,
    'auto_install': False,
    'application': True,
    'price': 75.00,
    'currency': 'USD',
    'images': ['static/description/banner.gif'],
    'license': 'OPL-1',
}