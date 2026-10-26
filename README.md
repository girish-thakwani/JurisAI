# PingPilot

Resilient, resumable outreach automation. Reads contacts from a Google Sheet (or CSV), sends through a
channel (WhatsApp Web today), and writes status back, surviving offline phones, dead internet, logouts,
crashes and API limits without sending duplicates.

> Use it only with people who have opted in. Bulk unsolicited messaging gets WhatsApp numbers banned.
> For large-scale outreach use the official WhatsApp Business API.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
playwright install chromium                              # only needed for the CDP client libs

cp .env.example .env                                     # fill in SHEET_URL, MESSAGE, ...
# put your Google service-account key at ./creds.json and share the sheet with its email

scripts/start_chrome.sh                                  # (Windows: scripts\start_chrome.bat)
# scan the WhatsApp QR once in that Chrome window

pingpilot run --dry-run     # rehearse the whole pipeline, sends nothing
pingpilot run               # the real thing
pingpilot status            # counts per status
pytest                      # tests (no browser or network needed)
```
Sheet columns: `A number | B status | C attempts | D updated`.
No Google credentials? `pingpilot run --csv contacts.csv` (see `contacts.example.csv`).

## Statuses
| Status | Meaning | Re-run behaviour |
|---|---|---|
| *(blank)* | pending | sent |
| `Completed` | delivered (clock icon cleared) | skipped |
| `In progress` | crashed between typing and confirmation | **skipped, check manually** (prevents duplicates) |
| `Review: ...` | outcome unknown or ambiguous | skipped, check manually |
| `Invalid: ...` | bad format / not on WhatsApp | skipped |
| `Duplicate` | same number appears earlier | skipped |
| `Failed: ...` | transient failure | retried until `MAX_ATTEMPTS` |

## Architecture
```
src/pingpilot/
├── cli.py            argparse entry point (run / status)
├── config.py         Settings from env/.env (one frozen dataclass, no globals)
├── runner.py         orchestration + policy: retries, batching, dedupe, circuit breaker
├── models.py         Contact, Status
├── control.py        Ctrl+C stop flag + interruptible sleep
├── net.py            internet probe / wait
├── journal.py        local append-only progress log (survives sheet outages)
├── messages.py       MessageProvider (static today, LLM tomorrow)
├── factory.py        picks source/channel from config
├── sources/          ContactSource: google_sheet, csv_source
└── channels/         Channel: whatsapp_web/ (selectors, browser, actions, channel), dry_run
```
Golden rule baked into `Runner`: anything **before** `channel.send()` is retried freely; anything
**after** it is never retried, it becomes `Review`.

## Extending
* **New source** (Airtable, Postgres, CRM): subclass `ContactSource`, register in `factory.py`.
* **New channel** (Telegram, SMS, email): subclass `Channel` (`ensure_ready / prepare / send`), register in `factory.py`.
* **WhatsApp UI changed**: edit only `channels/whatsapp_web/selectors.py`.
* **Smarter messages**: add a `MessageProvider` in `messages.py` (e.g. LLM-written variants per contact).

## Roadmap
- [ ] Reply triage (classify replies, auto do-not-contact list)
- [ ] LLM message variants with human-approved templates
- [ ] Self-healing selectors (vision/LLM locates the element when one breaks)
- [ ] Send-time optimisation from reply/join logs
- [ ] Lead scoring + FAQ-reply assistant (human in the loop)
- [ ] Anomaly alerts (failure spikes, restrictions) via Telegram/email
