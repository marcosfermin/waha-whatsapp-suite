# WhatsApp Suite (WAHA) — Odoo 18.0 edition

This folder contains the **Odoo 18.0** build of both modules, ported from the 17.0 edition:

- `waha_whatsapp_suite` — the main app
- `waha_whatsapp_helpdesk` — optional Helpdesk bridge (auto-installs with Helpdesk)

The technical module names are unchanged, so buyers install `waha_whatsapp_suite` exactly
as on 17 — just from this 18.0 package.

## Changes applied vs. the 17.0 edition

| Area | 17.0 | 18.0 |
|------|------|------|
| Manifest `version` | `17.0.1.0.0` | `18.0.1.0.0` |
| List views | `<tree>` … `</tree>` | `<list>` … `</list>` (Odoo 18 canonical tag) |
| Security check (`qr_controller.py`) | `check_access_rights('read')` + `check_access_rule('read')` | unified `check_access('read')` |
| Chatter flag (`models/mail_thread.py`) | 17-only `_get_mail_thread_data` + Store branch | Store-only `_thread_to_store`, signature-agnostic (`*args, **kwargs`) and wrapped in `try/except` so a Store-API change can never break the chatter |

Everything else (models, campaigns, automation, auto-replies, sync jobs, QR proxy/widget,
CRM/Sales/Project/Helpdesk glue) is identical to the 17.0 edition.

## Verify on a real Odoo 18 before publishing

- [ ] Both modules install and upgrade cleanly.
- [ ] **Chatter "Send WhatsApp" button** shows on partner / lead / order / ticket. This is the
      most version-sensitive piece — `mail_thread._thread_to_store` calls
      `store.add(self, {...}, as_thread=True)`. If the button is missing, the `try/except`
      is silently swallowing a Store-API mismatch for this minor release; adjust the `store.add`
      call to match.
- [ ] **QR widget** renders and flips to "Connected" (OWL field widget `waha_qr_code`,
      `@web/views/fields/standard_field_props`, `registry.category("fields")`).
- [ ] **Smart buttons** appear on crm.lead / sale.order / project.task / helpdesk.ticket —
      confirm the inherited view ids still exist: `crm.crm_lead_view_form`,
      `sale.view_order_form`, `project.view_task_form2`, `helpdesk.helpdesk_ticket_view_form`.
- [ ] **"Send WhatsApp" server action** appears in Settings → Automation Rules
      (`ir.actions.server` state extension + inherit of `base.view_server_action_form`).
- [ ] The res.partner form inherit xpath `//field[@name='mobile']` still resolves.
- [ ] List views render (the `<tree>`→`<list>` conversion).

## Migration
Model names / tables are the same as the 17.0 edition. Moving a database from the 17.0
build to this 18.0 build is a standard Odoo major-version upgrade of the same module.
