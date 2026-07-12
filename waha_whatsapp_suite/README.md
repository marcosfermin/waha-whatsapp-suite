# WhatsApp Suite (WAHA) for Odoo 19

A complete WhatsApp toolkit for Odoo built on the WAHA (WhatsApp HTTP API) service —
live chat, in-Odoo QR pairing, marketing campaigns, automation, auto-replies, a shared
inbox, phone sync, and CRM / Sales / Project / Helpdesk integration.

**Author:** Marcos Fermin — <https://www.marcosfermin.com>

## Features

- **Session Management**: Create and manage multiple WhatsApp sessions
- **In-Odoo QR Code**: Scan the live, auto-refreshing pairing QR right from the session form
- **Message Sending**: Send text messages, files, and voice messages
- **Template System**: Create and use message templates with variables
- **Contact Integration**: Link WhatsApp with Odoo contacts
- **Company Settings**: Set default WhatsApp session per company
- **Message History**: Track all sent and received messages
- **Campaigns**: Bulk messaging with throttling, scheduling and opt-out
- **Automation**: "Send WhatsApp" server action + inbound keyword auto-replies
- **Shared Inbox**: Assign and resolve conversations; canned replies
- **CRM / Sales / Project / Helpdesk** linking and analytics dashboards
- **Sync from Phone**: Import the phone's contacts and chat history (background or now)

## Requirements

- Odoo 19.0
- Depends on the **CRM**, **Sales**, **Project**, and **Automation Rules** (`base_automation`) apps
- Optional: the **Helpdesk** (Enterprise) app — its glue installs automatically via the
  companion `waha_whatsapp_helpdesk` module when both are present
- WAHA server (running via Docker)
- Python `requests` library

## Installation

1. **Setup WAHA Server**:
   ```bash
   # Start WAHA server (basic)
   docker run -it -p 3000:3000 devlikeapro/waha

   # Reference deployment (GOWS engine, API key, dashboard + Swagger auth)
   docker run -it -d \
     -e "WHATSAPP_DEFAULT_ENGINE=GOWS" \
     -e "WAHA_API_KEY=8d285bd2a7734d099f3fa0365b81869a" \
     -e "WAHA_DASHBOARD_USERNAME=admin" \
     -e "WAHA_DASHBOARD_PASSWORD=solucion" \
     -e "WHATSAPP_SWAGGER_USERNAME=admin" \
     -e "WHATSAPP_SWAGGER_PASSWORD=solucion" \
     -p 3000:3000 devlikeapro/waha
   ```

   Notes on the reference command:
   - `-d` runs the container detached (in the background).
   - `WAHA_API_KEY` secures the WAHA API. **Put the same value in the session's *API Key*
     field in Odoo** so requests are authenticated.
   - `WAHA_DASHBOARD_*` protect the WAHA dashboard (http://localhost:3000/dashboard) and
     `WHATSAPP_SWAGGER_*` protect the API docs (http://localhost:3000/). You do **not** need
     the dashboard for day-to-day use — the module scans the QR and manages sessions from Odoo.
   - The values above are examples — **change the API key and passwords for any real deployment.**

2. **Install Module**:
   - Copy the module folder(s) to your Odoo addons directory
   - Update the app list in Odoo
   - Install **WAHA WhatsApp Integration** (and, on Enterprise with Helpdesk, the
     auto-installing `waha_whatsapp_helpdesk` bridge)

3. **Configure**:
   - Go to **WhatsApp > Sessions > Manage Sessions** and create a session
   - Set the **WAHA Server URL** (default: http://localhost:3000), the **Engine**
     (GOWS recommended), and the **API Key** (must match `WAHA_API_KEY` above)
   - Click **Start Session**, then scan the QR code shown on the **QR Code** tab
     (it refreshes automatically and shows *Connected!* once linked)

## Usage

### Creating a Session

1. Navigate to **WhatsApp > Sessions > Manage Sessions**
2. Click **Create** and fill in:
   - Session Name
   - WAHA Server URL
   - Engine (GOWS recommended)
3. Click **Start Session**
4. Scan the QR code with your WhatsApp mobile app

### Sending Messages

#### From Contacts:
1. Open any contact
2. Set the WhatsApp Number field
3. Click the **Send WhatsApp** button

#### From WhatsApp Menu:
1. Go to **WhatsApp > Messages > Send Message**
2. Fill in the recipient details
3. Choose message type (text, file, or voice)
4. Send the message

### Using Templates

1. Create templates in **WhatsApp > Templates > Message Templates**
2. Use templates when sending messages for quick access to common messages

### Company Configuration

1. Go to **Settings > Companies > Companies**
2. Edit your company
3. In the **WhatsApp** tab, set the default session

## API Integration

The module provides the following key methods:

```python
# Start a session
session.action_start_session()

# Send text message
session.send_message(chat_id, text)

# Send file
session.send_message(chat_id, text, file_data, file_name, file_type)

# Send voice message
session.send_voice_message(chat_id, voice_data)
```

## Project Structure

```
waha_whatsapp_suite/            # main module
├── models/                      # sessions, messages, templates, campaigns,
│                                #   auto-replies, canned replies, conversations,
│                                #   sync jobs, "Send WhatsApp" server action,
│                                #   CRM / Sales / Project extensions
├── controllers/                 # inbound webhook + bus, chat & media proxy,
│                                #   authenticated QR proxy (/waha/session/qr)
├── wizard/                      # send message, add-to-campaign, sync-from-phone
├── views/                       # form/list/kanban/graph/pivot views + menus
├── security/                    # groups, record rules, ir.model.access.csv
├── data/                        # crons (status refresh, campaigns, sync jobs) + demo data
└── static/src/                  # JS/OWL widgets (incl. waha_qr_widget), XML templates, CSS

waha_whatsapp_helpdesk/            # optional bridge — auto-installs with Helpdesk (Enterprise)
```

## Extended Functionality

### Campaigns (Bulk messaging)
- **WhatsApp > Campaigns**: create a campaign, pick a session and a template/body,
  choose recipients (selected contacts or a saved contact filter), then **Send Now**
  or **Schedule**. Delivery is throttled (messages/minute) by a 1‑minute cron and each
  recipient's state (queued → sent → delivered → read / failed) is tracked.
- From the **Contacts** list, select several contacts → *Action → Add to WhatsApp Campaign*.
- Contacts flagged **WhatsApp Opt‑out** are automatically skipped.

### Automation (triggers)
- **Outbound**: in *Settings → Technical → Automation Rules*, add an action of type
  **Send WhatsApp**. It sends a template/message to each triggered record's contact —
  e.g. "Sale Order confirmed → WhatsApp the customer". Configure the session, template
  and the contact field path on the action.
- **Inbound**: **WhatsApp > Automation > Auto‑reply Rules** match incoming messages by
  keyword / regex and can reply from a template or free text, **attach images / files /
  audio** (the reply text is sent first, then each file as a separate message), opt the
  contact out (STOP keyword), add tags, assign the conversation, or create a CRM lead /
  Helpdesk ticket.

### Shared Inbox & Canned Replies
- **WhatsApp > Inbox**: a kanban/list of conversations (per session + chat) with
  assignment and Open/Pending/Resolved status, fed live from inbound messages.
- **WhatsApp > Automation > Canned Replies**: reusable quick replies with shortcuts.

### CRM / Sales / Project / Helpdesk
- Smart **WhatsApp** buttons on leads, sale orders, tasks (and tickets via the bridge)
  showing the message count and opening the conversation.
- Incoming messages can be turned into a **Lead** or **Helpdesk Ticket** in one click,
  and outbound messages sent from/about a record are logged into that record's chatter.
- Helpdesk is Enterprise‑only, so its glue ships as a separate **auto‑installing** module
  `waha_whatsapp_helpdesk` (installs automatically when both this module and Helpdesk are present).

### Reporting
- **WhatsApp > Reporting**: *Message Analytics* (graph/pivot by direction, status, session,
  date) and *Campaign Analytics* (sent/delivered/read/failed per campaign).

### Scan the QR code inside Odoo
- The session form's **QR Code** tab shows the live pairing code (via WAHA's
  `auth/qr` endpoint, so it works on every engine — NOWEB/GOWS/WEBJS), fetched through
  an authenticated Odoo proxy so the browser never touches WAHA or its API key.
- The code **auto-refreshes** while pairing and flips to **Connected!** as soon as the
  phone links — no need to open the WAHA dashboard.

### Sync from Phone (contacts + history)
- On a connected session, click **Sync from Phone** to import directly from the linked device:
  - **Contacts** → `res.partner` (optionally only contacts with a saved name; imported
    partners are tagged **WhatsApp**).
  - **Chats & Messages** → message log + Inbox conversations, with a configurable number
    of recent messages per chat and an option to include group chats.
- Imported messages keep their original WhatsApp timestamps. The sync commits per chat, so
  a long run that is interrupted keeps its progress, and re-running is safe (nothing is
  duplicated — messages are de-duplicated on their WAHA id).
- **Background mode (recommended)**: the wizard queues a **Sync Job** that a scheduler
  processes a few chats at a time (every ~2 minutes), so nothing blocks or times out. Watch
  progress, cancel, or re-run under **WhatsApp > Sessions > Sync Jobs**; tune *Chats per run*
  on the job for faster/slower imports. Choose *Now* instead to run synchronously for small
  accounts.
- Requires the engine **Store** (NOWEB/GOWS): the module enables it automatically when the
  session starts. Last contacts/messages sync times are shown on the session form.

## Troubleshooting

### Common Issues:

1. **Session won't start**: Check WAHA server URL and ensure WAHA is running
2. **QR Code not showing**: Refresh the session status and try getting QR code again
3. **Messages not sending**: Verify session status is "Working"
4. **Connection errors**: Check firewall settings and network connectivity

### Logs:
Check Odoo logs for detailed error messages:
```bash
tail -f /var/log/odoo/odoo.log | grep -i waha
```

## Support

For issues and questions, contact **Marcos Fermin**:
- https://www.marcosfermin.com

## License

This module is licensed under OPL-1.

© Marcos Fermin — https://www.marcosfermin.com