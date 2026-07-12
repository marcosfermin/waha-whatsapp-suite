# WhatsApp Suite (WAHA) — Odoo 19.0 edition

This folder contains the **Odoo 19.0** build of both modules, ported from the 17.0 edition:

- `waha_whatsapp_suite` — the main app
- `waha_whatsapp_helpdesk` — optional Helpdesk bridge (auto-installs with Helpdesk)

The technical module names are unchanged, so buyers install `waha_whatsapp_suite` exactly
as on 17 — just from this 19.0 package.

## Changes applied vs. the 17.0 edition

| Area | 17.0 | 19.0 |
|------|------|------|
| Manifest `version` | `17.0.1.0.0` | `19.0.1.0.0` |
| List views | `<tree>` … `</tree>` | `<list>` … `</list>` |
| Security check (`qr_controller.py`) | `check_access_rights('read')` + `check_access_rule('read')` | unified `check_access('read')` |
| Chatter flag (`models/mail_thread.py`) | 17-only `_get_mail_thread_data` + Store branch | Store-only `_thread_to_store`, signature-agnostic (`*args, **kwargs`) and wrapped in `try/except` |

The code is otherwise identical to the 18.0 edition.

## ⚠️ Odoo 19 — higher-risk areas to verify

Odoo 19 is newer and moves faster than 18; these are the spots most likely to need a tweak.
The code is written defensively so nothing should hard-crash, but confirm behaviour:

- [ ] **Chatter "Send WhatsApp" button** (`mail_thread._thread_to_store` →
      `store.add(self, {...}, as_thread=True)`). Odoo 19's mail **Store API** is the single
      most likely thing to have changed. The call is wrapped in `try/except`, so if it no
      longer matches, the button just won't appear (no crash) — update `store.add` to the
      19 signature.
- [ ] **`res.partner` `mobile` field** — the WhatsApp number is computed from `mobile`/`phone`
      and the partner form inherits at `//field[@name='mobile']`. Confirm the field/xpath
      still exist on 19; adjust if the contact form changed.
- [ ] **Inherited view ids** still exist: `crm.crm_lead_view_form`, `sale.view_order_form`,
      `project.view_task_form2`, `helpdesk.helpdesk_ticket_view_form`, `base.view_partner_form`,
      `base.view_server_action_form`.
- [ ] **OWL field widget** `waha_qr_code` (`standardFieldProps`, `registry.category("fields")`)
      and the other JS/OWL components render correctly.
- [ ] **`ir.actions.server` state extension** ("Send WhatsApp" action) and the
      `_run_action_waha_whatsapp_multi` dispatch still work.
- [ ] List views render (the `<tree>`→`<list>` conversion).

## Migration
Model names / tables match the other editions — a standard Odoo major-version upgrade.
