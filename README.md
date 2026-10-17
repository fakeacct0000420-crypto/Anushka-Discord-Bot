# Anushka — Discord Moderation Bot

A powerful, fully autonomous Discord moderation bot with a strike-based escalation system, anti-nuke protection, music playback, and dynamic role-based permissions backed by MongoDB.

## ✨ Features

| Module | Commands |
|--------|----------|
| **Moderation** | `!kick` `!ban` `!unban` `!timeout` `!untimeout` `!purge` |
| **AutoMod** | `!warn` `!strikes` `!clearstrikes` (auto-escalates through 5 tiers) |
| **AntiNuke** | Passive protection — monitors mass bans/kicks/deletions |
| **Music** | `!play` `!skip` `!pause` `!resume` `!stop` `!queue` `!loop` `!volume` |

## ⚙️ Strike Escalation

| Strike | Punishment |
|--------|-----------|
| 1st | DM warning |
| 2nd | 15-minute timeout |
| 3rd | 12-hour timeout |
| 4th | Kick |
| 5th+ | Permanent ban |

## 🚀 Setup

```bash
# 1. Clone the repo
git clone https://github.com/<your-username>/anushka-discord-bot.git
cd anushka-discord-bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env → fill in DISCORD_TOKEN and MONGO_URI

# 4. Run the bot
python core.py
```

## 🛡️ First-time Discord setup

```
!setmodrole @YourModRole
!setmusicrole @YourDJRole
!setlockdownrole @Quarantine
!setlogchannel #mod-logs
```

## 📦 Tech Stack

- **discord.py** 2.3+ — Discord gateway & voice
- **Motor** — Async MongoDB driver
- **yt-dlp** — Audio extraction for music
- **FFmpeg** — Audio encoding (must be on PATH)
- **python-dotenv** — Environment management

## 📋 Requirements

- Python 3.11+
- MongoDB (local or Atlas)
- FFmpeg (for music commands)
