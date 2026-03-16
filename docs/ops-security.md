# Telegram Research Agent — Operations and Security

**Version:** 1.0.0
**Date:** 2026-03-16
**Status:** Baseline

---

## Overview

This document defines the operational model and security requirements for the Telegram Research Agent running on a private Ubuntu 22.04 VPS.

The system is not internet-facing. All security decisions optimize for isolation, minimal attack surface, and protection of Telegram account credentials.

---

## Threat Model

| Threat | Likelihood | Mitigation |
|---|---|---|
| Telegram session file leaked | Medium (if workspace is exposed) | Session stored in `/srv/openclaw-you/secrets/`, not in workspace |
| API credentials in source code | High risk (common mistake) | Enforced by review checklist; `.gitignore` covers `.env` files |
| LLM gateway exposed to network | Low (local binding) | Gateway bound to `127.0.0.1:18789` only |
| Process running as root | Medium | All services run as `oc_you` user |
| DB readable by other users | Low | DB permissions set to `640`, owned by `oc_you` |
| OpenClaw runtime tampered with | Low | Source at `/opt/openclaw/src` is read-only; ownership checked in review |
| SSH brute force | Mitigated at infra level | SSH restricted by IP, UFW enabled |

---

## Secrets Management

### What Is a Secret

The following are secrets and must never appear in source code, config files, or logs:

- Telegram API `api_id`
- Telegram API `api_hash`
- Telegram account phone number
- Telethon session binary (`.session` file)
- Any OpenClaw gateway auth tokens (if present)

### Where Secrets Live

All secrets are stored in:

```
/srv/openclaw-you/secrets/
├── telegram_api.env     ← api_id, api_hash, phone number (600)
└── telegram.session     ← Telethon binary session file (600)
```

**Permissions:**
```bash
chmod 600 /srv/openclaw-you/secrets/telegram_api.env
chmod 600 /srv/openclaw-you/secrets/telegram.session
chown oc_you:oc_you /srv/openclaw-you/secrets/telegram_api.env
chown oc_you:oc_you /srv/openclaw-you/secrets/telegram.session
```

### How Secrets Are Accessed

Application code reads credentials from environment variables only.

`telegram_api.env` format:
```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
TELEGRAM_PHONE=+1234567890
TELEGRAM_SESSION_PATH=/srv/openclaw-you/secrets/telegram.session
```

This file is sourced by systemd via `EnvironmentFile=` directive and by `scripts/setup.sh` for the initial auth flow.

Application code loads these via `os.environ`, never via hardcoded values.

### .gitignore Requirements

The following must appear in `.gitignore`:

```
data/agent.db
data/agent.db-wal
data/agent.db-shm
*.session
*.env
__pycache__/
*.pyc
.env
```

---

## Network Security

### Gateway Access

The OpenClaw LLM gateway is only accessible locally:

```
ws://127.0.0.1:18789
```

No process outside the VPS can reach it. No firewall exception is needed or permitted for this port.

### Telegram MTProto

Telethon connects outbound to Telegram's MTProto servers over the public internet. This is the only external network connection the agent makes.

No inbound ports are opened by the agent. UFW rules are not modified by agent code.

### No HTTP Server

The agent does not start any HTTP server. Output is written to files in `data/output/`. There is no web interface in MVP.

---

## File System Security

### Ownership and Permissions

| Path | Owner | Mode | Notes |
|---|---|---|---|
| `/srv/openclaw-you/secrets/` | `oc_you:oc_you` | `700` | No world/group read |
| `/srv/openclaw-you/secrets/telegram.session` | `oc_you:oc_you` | `600` | Session binary |
| `/srv/openclaw-you/secrets/telegram_api.env` | `oc_you:oc_you` | `600` | API credentials |
| `data/agent.db` | `oc_you:oc_you` | `640` | SQLite database |
| `data/output/` | `oc_you:oc_you` | `750` | Output Markdown files |
| `/srv/openclaw-you/workspace/telegram-research-agent/` | `oc_you:oc_you` | `750` | Project workspace |

### OpenClaw Source (Read-Only)

`/opt/openclaw/src` must remain unmodified. Any modification to OpenClaw source is a security and integrity violation. Review checklist enforces this.

---

## Systemd Hardening

All agent systemd services must include the following hardening directives:

```ini
[Service]
User=oc_you
Group=oc_you
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/srv/openclaw-you/workspace/telegram-research-agent/data
ReadWritePaths=/srv/openclaw-you/secrets
ProtectHome=true
```

These directives:
- Prevent privilege escalation (`NoNewPrivileges`)
- Isolate `/tmp` (`PrivateTmp`)
- Make system directories read-only (`ProtectSystem=strict`)
- Explicitly allow writes only to designated paths (`ReadWritePaths`)
- Prevent access to home directories (`ProtectHome`)

---

## Operational Runbook

### Initial Setup

```bash
# 1. Create secrets directory (if not present)
sudo -u oc_you mkdir -p /srv/openclaw-you/secrets
sudo chmod 700 /srv/openclaw-you/secrets

# 2. Create telegram_api.env
sudo -u oc_you nano /srv/openclaw-you/secrets/telegram_api.env
# Fill in TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, TELEGRAM_SESSION_PATH

# 3. Run setup (interactive Telegram auth + DB migration)
cd /srv/openclaw-you/workspace/telegram-research-agent
sudo -u oc_you bash scripts/setup.sh

# 4. Run bootstrap ingestion (one-time)
sudo -u oc_you bash scripts/run_bootstrap.sh

# 5. Install and enable systemd timers
sudo cp systemd/telegram-ingest.service /etc/systemd/system/
sudo cp systemd/telegram-ingest.timer /etc/systemd/system/
sudo cp systemd/telegram-digest.service /etc/systemd/system/
sudo cp systemd/telegram-digest.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-ingest.timer
sudo systemctl enable --now telegram-digest.timer
```

### Checking Service Status

```bash
systemctl status telegram-ingest.timer
systemctl status telegram-digest.timer
journalctl -u telegram-ingest.service -n 50
journalctl -u telegram-digest.service -n 50
```

### Checking Output

```bash
ls -la /srv/openclaw-you/workspace/telegram-research-agent/data/output/digests/
cat /srv/openclaw-you/workspace/telegram-research-agent/data/output/digests/$(date +%Y-W%V).md
```

### Checking the Database

```bash
sudo -u oc_you sqlite3 /srv/openclaw-you/workspace/telegram-research-agent/data/agent.db \
  "SELECT channel_username, COUNT(*) FROM raw_posts GROUP BY channel_username;"
```

### Restarting the Weekly Pipeline Manually

```bash
sudo -u oc_you bash /srv/openclaw-you/workspace/telegram-research-agent/scripts/run_weekly.sh
```

### Health Check

```bash
sudo -u oc_you bash /srv/openclaw-you/workspace/telegram-research-agent/scripts/healthcheck.sh
```

Healthcheck verifies:
- DB file exists and is readable
- OpenClaw gateway is reachable at `ws://127.0.0.1:18789`
- Session file exists at expected path
- Last ingestion timestamp is within 8 days

---

## Log Retention

systemd journal handles log rotation automatically. Default retention is 7 days or 100 MB depending on VPS configuration.

No additional log rotation configuration is required for MVP.

If output volume becomes significant, add:
```bash
sudo journalctl --vacuum-time=30d
```

---

## Incident Response

### Telegram Session Compromised

1. Immediately revoke the session via Telegram's "Active Sessions" settings.
2. Delete `/srv/openclaw-you/secrets/telegram.session`.
3. Re-run `scripts/setup.sh` to create a new session.
4. Audit recent pipeline runs via journal to determine scope.

### Database Corrupted

SQLite WAL mode reduces corruption risk. If corruption occurs:
1. Stop timers: `sudo systemctl stop telegram-ingest.timer telegram-digest.timer`
2. Check journal for the failing operation.
3. Run `sqlite3 data/agent.db "PRAGMA integrity_check;"`
4. If corrupt: restore from last known good backup (manual process; backup strategy is post-MVP).
5. Re-run bootstrap for affected channels if needed.

### OpenClaw Gateway Unreachable

1. Check `systemctl status openclaw-you.service`
2. Restart if needed: `sudo systemctl restart openclaw-you.service`
3. Digest pipeline will fail gracefully and log the error.
4. Ingestion pipeline does not depend on OpenClaw; it can proceed independently.

---

## Review Gates for Security (per phase)

Before each phase is marked complete, Claude Reviewer checks:

- [ ] No secrets in any `src/` file
- [ ] No secrets in any `systemd/` file
- [ ] Session path is loaded from env var, not hardcoded
- [ ] Systemd service specifies `User=oc_you`
- [ ] Systemd service specifies `NoNewPrivileges=true`
- [ ] No new ports opened
- [ ] `.gitignore` updated if new sensitive file types introduced
- [ ] No modifications to `/opt/openclaw/src`
