# WhatsApp Suite (WAHA) — Odoo 17.0 edition

This folder contains the **Odoo 17.0** build of both modules — the baseline edition that the
18.0 and 19.0 packages are ported from:

- `waha_whatsapp_suite` — the main app
- `waha_whatsapp_helpdesk` — optional Helpdesk bridge (auto-installs with Helpdesk)

Install `waha_whatsapp_suite` from this folder on an Odoo 17.0 server. See the module's own
`waha_whatsapp_suite/README.md` for full setup, WAHA server instructions, and the feature list.

## This is the baseline

There is nothing to "port" here — this is the original 17.0 code. The 18.0 and 19.0 editions
(in `../odoo18/` and `../odoo19/`, each with its own `PORTING_NOTES.md`) apply these deltas on
top of this baseline:

| Area | 17.0 (here) | 18.0 / 19.0 |
|------|-------------|-------------|
| Manifest `version` | `17.0.1.0.0` | `18.0.1.0.0` / `19.0.1.0.0` |
| List views | `<tree>` … `</tree>` | `<list>` … `</list>` |
| Security check (`qr_controller.py`) | `check_access_rights` + `check_access_rule` | unified `check_access('read')` |
| Chatter flag (`models/mail_thread.py`) | `_get_mail_thread_data` (17) + Store branch | Store-only, defensive `_thread_to_store` |

## Requirements

- Odoo 17.0
- Apps: CRM, Sales, Project, Automation Rules (`base_automation`); Helpdesk (Enterprise) optional
- A running WAHA server (see `waha_whatsapp_suite/README.md`)

Author: **Marcos Fermin** — https://www.marcosfermin.com
