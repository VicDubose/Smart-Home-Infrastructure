# JARVIS Finance B — SimpleFIN Bridge Re-Authorization: Hardening Note

*Installed version: v1.11 (2026-11-12) · Host: SKYNET (192.168.50.51) · Owner: Victor*

## 1. What it does

SimpleFIN Bridge keeps losing two bank connections:
- **Regions** asks to re-verify about once a day, with 1 of 3 security questions.
- **Dovenmuehle (mortgage)** asks about once a week, with a 6-digit passcode emailed to Gmail.

While a connection is in that state, the 06:40 and 18:40 bank sync pulls nothing for that bank. This program signs into SimpleFIN Bridge on a schedule and clicks **Adjust** on each of those connections. It then completes the check the bank asks for: the security answer for Regions, or the emailed passcode for the mortgage. The next bank sync then gets fresh data.

**What it never does:**
- holds a bank username or password (SimpleFIN keeps those);
- moves money;
- changes anything in Actual or Home Assistant;
- prints an answer, passcode, sign-in link or question text.

## 2. How a run works

1. **Sign in with its own passkey.** The script signs into SimpleFIN with a passkey it created for itself, through Chrome's virtual authenticator (`SIGNED_IN_WITH_PASSKEY`). No email and no human check are needed.
   - Why a passkey: SimpleFIN's email sign-in page has a Cloudflare "verify you are human" check. That check is deliberately **not** bypassed.
   - Why not a saved session: SimpleFIN sessions are session-only cookies, so a session can't be saved either.
2. **Read the status table.** It opens **My account** and reads the Financial Institutions table (`STATUS ...`).
3. **Decide which connections to open**, under the schedule and limits in §3.
4. **Click Adjust and handle the screens.** It watches the screen inside the bank's iframe and classifies it as one of these:

| Screen | What the script does |
|---|---|
| busy | waits |
| success | clicks Done → `ok` |
| choice ("use security questions?") | picks security questions, Continue |
| question (Regions) | matches the question to **exactly one** stored keyword set, submits that answer. No match → stops (`no_answer_match`) |
| passcode (mortgage) | if asked where to send it, picks email. Then reads Gmail label `jarvis-auth-mortgage` (read-only IMAP) for a passcode email that arrived **after** the click and names loan **…5675**. Waits up to 10 min, enters it |
| credentials | stops (`needs_full_login`): the bank wants a full login, which only you can do |
| unknown for 45 s | stops (`unknown_screen`) and saves a screenshot |

5. **Re-read the status table** (`STATUS_AFTER`). If a connection went from *Auth required* to *OK* but the last screen was unfamiliar, it still counts as `ok` (`VERIFIED_BY_STATUS`).
6. **Save and report.** It writes `last_result.json` and sends **one** alert per problem per day.

## 3. Schedule and safety limits

| What | Rule |
|---|---|
| Twice-a-day run | **05:20 and 17:20** CT (+0–2 min random); catches up after a reboot. Both finish ~80 min before the 06:40 / 18:40 bank sync |
| Reactive check | every **3 h at :40** (00:40 … 21:40, +0–5 min). Acts **only** on a connection showing *Auth required*. Does nothing in observe mode |
| Regions | opened on both scheduled runs; **max 2 opens/day** in total |
| Mortgage | scheduled **Mon / Wed / Fri** at 05:20. **Max 1 open/day** and **3 opens per rolling 7 days**, counting reactive checks. Every Adjust triggers a passcode email, so opens are what's counted |
| Answers / codes | **hard max 2 submissions per bank per day**; never answers the same question twice; a rejected answer counts |
| Manual runs | `install.sh mortgage` / `regions` skip the schedule and the open limits but **count** toward them; the 2-submission limit still applies |
| Concurrency | one run at a time (`run.lock`). A second run waits up to 25 min, then skips |

## 4. Where things live

| Item | Location |
|---|---|
| Program + installer | `~/rdp-scripts/Jarvis/finance/ops/tools/jarvis_bridge_reauth_v1/` (`install.sh`, `run.sh`, `pack_creds.py`, `app/`, `tests/`) |
| Container | `jarvis-bridge-reauth:v1` (Playwright 1.49.1 / Chromium, Xvfb) |
| Config | `/etc/jarvis-bridge-reauth/config.json` (root:onsiteadmin 640): mode, bridge URL, Gmail labels, per-bank rules, `schedule_version: 2`, HA URL + webhook id |
| Secrets | `/etc/jarvis-bridge-reauth/*.cred`, encrypted with `systemd-creds`: `gmail_user`, `gmail_app_password` (copied from the al-power Gmail login), `regions_qa` (3 keyword sets + answers), `bridge_passkey` |
| Units | `jarvis-bridge-reauth@.service` (profiles: `daily`, `reactive`, `mortgage-live/observe`, `regions-live/observe`), `jarvis-bridge-reauth.timer`, `jarvis-bridge-reauth-check.timer` |
| State | `~/.local/share/jarvis-bridge-reauth/` (see list below) |
| Logs | `journalctl -u 'jarvis-bridge-reauth*'` |
| HA automation (not installed yet) | `~/jarvis_bridge_reauth_ha_automation.yaml` |

**What's in the state folder:**
- `profile/`: the browser profile.
- `attempts.json`: answer/code submissions today.
- `opens.json`: Adjust opens, kept for 14 days.
- `notified.json`: alerts already sent today.
- `passkey_counter.json`: the passkey's sign-in counter.
- `last_result.json`: the last run's results.
- `shots/`: screenshots.

**How secrets reach the program:** systemd decrypts the `.cred` files only for the length of a run. `pack_creds.py` pipes them as JSON into the container's stdin. They never touch disk, process arguments or environment variables.

## 5. Commands

All commands are `bash ~/rdp-scripts/Jarvis/finance/ops/tools/jarvis_bridge_reauth_v1/install.sh <command>`.

| Command | Use |
|---|---|
| `status` | timers, mode, today's attempts, last result |
| `live 05:20 17:20` | live mode, both timers on |
| `observe` | observe-only (opens screens, submits nothing), both timers off |
| `mortgage` / `mortgage observe` | mortgage only, now |
| `regions` / `regions observe` | Regions only, now |
| `check` | run the reactive check now |
| `run` | one run of the twice-a-day job now |
| `login` | **re-create the passkey** (needs a MobaXterm X11 session). You sign in by hand in a normal browser window, then click *My account → Add a Passkey* |
| `secrets` | re-enter the Gmail login or the Regions answers |
| `uninstall` | removes units + image; keeps secrets and state |

## 6. When it alerts you, and what to do

| Result | Meaning | Fix |
|---|---|---|
| `needs_login` / `passkey_failed` | the passkey no longer works (removed in SimpleFIN, or the profile was wiped) | `install.sh login` |
| `no_answer_match` | Regions asked a question that matches none of the stored keyword sets | `install.sh secrets` (fix keywords), then `install.sh regions` |
| `limit_reached` | 2 answers/codes already tried today | finish by hand in SimpleFIN; it resets tomorrow |
| `no_passcode_email` | no mortgage email in the label within 10 min | check that the Gmail filter still labels mail from `noreply@yourmortgageonline.com` as `jarvis-auth-mortgage` |
| `week_limit` | mortgage still needs auth after 3 opens this week | finish by hand in SimpleFIN |
| `needs_full_login` | the bank wants a full username/password login | do it in SimpleFIN Bridge |
| `unknown_screen` / `timeout` / `error` | something new on the page | screenshots are in `shots/<time>/`; run `install.sh mortgage observe` or `regions observe` to look safely |

`not_due`, `opened_today` and `observed` are normal results, not problems.

## 7. Verification record (2026-11-12)

- 18 self-tests pass inside the container on every install. They run against a mock SimpleFIN site (no network) and cover:
  - passkey sign-in;
  - Regions question, choice screen, wrong answer → stops at 2;
  - mortgage passcode with an email-channel choice;
  - unfamiliar final screen;
  - reactive-only runs;
  - once-a-day and 3-a-week mortgage limits;
  - one alert per day;
  - page-change retries.
- Live runs:
  - Passkey sign-in worked: `SIGNED_IN_WITH_PASSKEY` in ~2 s.
  - Regions: Adjust gave `ok` (no question was asked that day).
  - **Mortgage end-to-end at 02:56:** *Auth required* → passcode read from Gmail and entered → *OK*.
- Live since 03:12 CT. The first reactive check at 03:43 opened nothing, because both connections were OK.

## 8. Known gaps and next steps

- **Alerts aren't wired up yet.** The script posts to the HA webhook, but no HA automation is installed, so alerts go nowhere. Plan: an HA dashboard flag plus Apple Home notification (HA YAML to be provided; Jarvis does not edit HA).
- **The Regions security-question path hasn't happened live yet.** So far Regions re-synced without asking. The first real question will show `ANSWER_SUBMITTED` or `no_answer_match` in the log.
- **Leftover unit:** the old non-template `jarvis-bridge-reauth.service` is still installed but unused.
- **Out-of-date install text:** the install's "timer stays off until live" line is wrong when the timers are already live.
- **Overlap:** the 06:40 and 18:40 reactive checks start at the same time as the bank sync. This is harmless, and the check could be moved to :10 if wanted.
- **Unused label:** the Gmail label `jarvis-auth-simplefin` was for the abandoned email sign-in.

**Version history (short):**
- v1–v1.5: email sign-in, blocked by Cloudflare.
- v1.6–v1.7: by-hand login and passkey.
- v1.8: safe return after Done.
- v1.9: mortgage-only runs and timers.
- v1.10: status-verified success.
- v1.11: schedule limits.
