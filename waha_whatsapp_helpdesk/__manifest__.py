{
    'name': 'WhatsApp Suite (WAHA) - Helpdesk Bridge',
    'version': '17.0.1.0.0',
    'category': 'Marketing',
    'summary': 'Link WhatsApp conversations to Helpdesk tickets',
    'description': '''
        Optional bridge between WhatsApp Suite (WAHA) and Helpdesk.
        Adds a WhatsApp smart button on tickets and lets agents create/link
        tickets from incoming WhatsApp messages.

        Install this only if you use the Helpdesk (Enterprise) application.
    ''',
    'author': 'Marcos Fermin',
    'website': 'https://www.marcosfermin.com',
    'depends': ['waha_whatsapp_suite', 'helpdesk'],
    'data': [
        'views/helpdesk_ticket_views.xml',
    ],
    'price': 50.00,
    'currency': 'USD',
    'images': ['static/description/icon.png'],
    'installable': True,
    'auto_install': True,
    'application': False,
    'license': 'OPL-1',
}
