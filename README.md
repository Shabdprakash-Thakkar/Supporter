# Supporter BOT

<div align="center">

![Supporter BOT](https://img.shields.io/badge/Discord-Bot-5865F2?style=for-the-badge&logo=discord&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-2.0+-000000?style=for-the-badge&logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791?style=for-the-badge&logo=postgresql&logoColor=white)

**A powerful, multi-functional Discord bot with a modern web dashboard for complete server management and user engagement.**

[Features](#-features) • [Dashboard](#-web-dashboard) • [Commands](#-command-reference) • [Installation](#-installation) • [Support](#-support)

</div>

---

## 🌟 Overview

Supporter BOT is an all-in-one Discord server management solution designed to automate tedious tasks and boost community engagement. Whether you're running a small friend group or a large community server, Supporter BOT provides the tools you need to create an active, well-moderated, and engaging environment.

### Why Choose Supporter BOT?

- **🎯 Easy Setup** - Get started in minutes with intuitive slash commands
- **🌐 Web Dashboard** - Configure everything through a beautiful, modern interface
- **🔒 Secure** - Discord OAuth2 authentication and permission-based access
- **📊 Real-time Stats** - Track server activity and bot performance live
- **🔄 Always On** - 99.9% uptime with automatic recovery

---

## ✨ Features

### 🏆 Advanced Leveling System

Engage your community with a comprehensive XP and leveling system that rewards active members.

| Activity | XP Earned | Notes |
|----------|-----------|-------|
| Text Message | 10 XP | Per message sent |
| Image/Media Message | 15 XP | Messages with attachments |
| Voice Activity | 4 XP/minute | Capped at configurable limit |

**Key Features:**
- **Automatic Role Rewards** - Assign roles when users reach specific levels
- **Server Leaderboard** - Foster healthy competition with rankings
- **Level-up Announcements** - Celebrate achievements in a dedicated channel
- **Auto-Reset Scheduling** - Perfect for seasonal events (1-365 days)
- **Manual Reset** - Instantly reset all XP and remove reward roles
- **Configurable XP Rates** - Customize XP values via the dashboard

### 📺 YouTube Notifications

Never miss content from your favorite creators with automatic upload notifications.

- **RSS-Based Monitoring** - No API quota limits, reliable detection
- **Custom Messages** - Use placeholders for dynamic content
- **Role Mentions** - Ping specific roles or @here/@everyone
- **Channel Finder** - Easily find any YouTube channel's ID
- **Feed Testing** - Preview RSS results before going live

**Supported Placeholders:**
```
{channel_name} - YouTube channel name
{video_title}  - Video title
{video_url}    - Direct video link
{@role}        - Configured role mention
{@here}        - @here mention
{@everyone}    - @everyone mention
```

### 🛡️ Granular Channel Restrictions V2

The most powerful content filtering system available, with both legacy presets and granular control.

#### Legacy Presets (Quick Setup)
| Preset | Description |
|--------|-------------|
| **Block Discord Invites** | Only blocks discord.gg links |
| **Block All Links** | Blocks all HTTP/HTTPS URLs |
| **Media Only** | Only allows images, videos, attachments |
| **Text Only** | Only allows plain text messages |

#### Granular Control (Advanced)
Create custom combinations by allowing or blocking specific content types:

| Content Type | Description |
|--------------|-------------|
| Plain Text | Regular text messages |
| Discord Invites | discord.gg/... links |
| Image Links | URLs ending in .png, .jpg, .gif, etc. |
| Regular Links | Other HTTP(S) URLs |
| Image Attachments | Uploaded image files |
| File Attachments | Uploaded non-image files |
| Embeds | Rich embed content |

**Example Combinations:**
- Allow text + regular links, block Discord invites
- Allow only images, block everything else
- Allow text + images, block all links

**Features:**
- **Redirect Channel** - Guide users to the correct channel
- **Role Bypass** - Allow moderators to bypass restrictions
- **Visual Management** - Configure everything via the dashboard

### ⏰ Live Time Channels

Keep your international community synchronized with auto-updating voice channels.

- **📅 Date Channel** - Shows current date
- **🇮🇳 India Time (IST)** - Indian Standard Time
- **🇯🇵 Japan Time (JST)** - Japan Standard Time

*Updates every 10 minutes for accurate timekeeping*

### 👑 Owner Controls

Bot owners have exclusive access to powerful management commands:

- View all servers the bot is in
- Force leave any server
- Ban/unban servers from using the bot
- Force update statistics

---

## 🌐 Web Dashboard

A modern, responsive web dashboard built with Flask and Bootstrap 5.

### Dashboard Features

- **🔐 Discord OAuth2 Login** - Secure authentication
- **📊 Live Statistics** - Server count, user count, commands used
- **⚙️ Server Configuration** - Manage all settings visually
- **🎨 Dark/Light Mode** - Toggle between themes
- **📱 Mobile Responsive** - Works on all devices

### Dashboard Sections

| Section | Features |
|---------|----------|
| **General** | XP rates, voice XP limit configuration |
| **Leveling** | Role rewards, leaderboard, auto-reset, manual reset |
| **Time Channels** | Enable/disable, channel selection |
| **YouTube** | Add/edit/delete notification configurations |
| **Channel Restrictions** | Full granular control with visual editor |

### Access Control

- Only server **Administrators** and **Owners** can access the dashboard
- Users can only see servers where they have admin permissions
- All actions are logged for security

---

## 📋 Command Reference

### General Commands (3)

| Command | Description | Permission |
|---------|-------------|------------|
| `/ping` | Check bot latency and live stats | Everyone |
| `/g1-help` | Show all available commands | Everyone |
| `/g2-show-config` | Display server configuration | Manage Guild |

### Leveling Commands (10)

| Command | Description | Permission |
|---------|-------------|------------|
| `/l1-level` | Check your or another user's level | Everyone |
| `/l2-leaderboard` | Show top 10 users | Everyone |
| `/l3-setup-level-reward` | Set role reward for a level | Manage Roles |
| `/l4-level-reward-show` | View all level rewards | View Audit Log |
| `/l5-notify-level-msg` | Set level-up announcement channel | Manage Channels |
| `/l6-set-auto-reset` | Schedule automatic XP reset | Administrator |
| `/l7-show-auto-reset` | Show auto-reset configuration | Administrator |
| `/l8-stop-auto-reset` | Disable auto-reset | Administrator |
| `/l9-reset-xp` | Manually reset all XP and roles | Administrator |
| `/l10-upgrade-all-roles` | Sync roles for all users | Manage Roles |

### YouTube Commands (5)

| Command | Description | Permission |
|---------|-------------|------------|
| `/y1-find-youtube-channel-id` | Find channel ID from @handle or URL | Everyone |
| `/y2-setup-youtube-notifications` | Configure notifications for a channel | Manage Guild |
| `/y3-disable-youtube-notifications` | Remove notification configuration | Manage Guild |
| `/y4-list-youtube-notifications` | List all configured notifications | Manage Guild |
| `/y5-test-rss-feed` | Test RSS feed and preview results | Manage Guild |

### Channel Restriction Commands (11)

| Command | Description | Permission |
|---------|-------------|------------|
| `/n1-setup-no-text` | Configure media-only channel | Manage Channels |
| `/n2-remove-no-text` | Remove media-only restriction | Manage Channels |
| `/n3-bypass-no-text` | Add role to bypass restrictions | Manage Roles |
| `/n4-show-bypass-roles` | Show all bypass roles | Manage Roles |
| `/n5-remove-bypass-role` | Remove role bypass ability | Manage Roles |
| `/n6-no-discord-link` | Block Discord invite links only | Manage Channels |
| `/n7-no-links` | Block ALL links | Manage Channels |
| `/n8-remove-no-discord-link` | Remove Discord link blocking | Manage Channels |
| `/n9-remove-no-links` | Remove all link blocking | Manage Channels |
| `/n10-setup-text-only` | Configure text-only channel | Manage Channels |
| `/n11-remove-text-only` | Remove text-only restriction | Manage Channels |

### Time Channel Commands (1)

| Command | Description | Permission |
|---------|-------------|------------|
| `/t1-setup-time-channels` | Set up date and time channels | Manage Channels |

### Owner Commands (4)

| Command | Description | Permission |
|---------|-------------|------------|
| `/g3-serverlist` | List all servers bot is in | Bot Owner |
| `/g4-leaveserver` | Force bot to leave a server | Bot Owner |
| `/g5-banguild` | Ban a server from using the bot | Bot Owner |
| `/g6-unbanguild` | Unban a server | Bot Owner |

**Total Commands: 34**

---

## 📂 Project Structure

```
Supporter/
│
├── run_production.py              # Main startup script (bot + web)
│
├── Python_Files/                  # Discord Bot Core
│   ├── supporter.py               # Main bot, events, command tree
│   ├── level.py                   # Leveling system & XP management
│   ├── no_text.py                 # Channel restrictions (V2 granular)
│   ├── date_and_time.py           # Auto-updating time channels
│   ├── youtube_notification.py    # YouTube RSS monitoring
│   ├── owner_actions.py           # Owner-only commands
│   └── help.py                    # Help command system
│
├── Flask_Frontend/                # Web Dashboard
│   ├── app.py                     # Flask app, routes, API endpoints
│   ├── templates/                 # Jinja2 HTML templates
│   │   ├── base.html              # Base template (navbar, footer)
│   │   ├── index.html             # Homepage with features & stats
│   │   ├── contact.html           # Contact form page
│   │   ├── dashboard.html         # Server selection page
│   │   ├── server_config.html     # Server configuration page
│   │   ├── iframe_base.html       # Base for iframe content
│   │   └── channel_restrictions_v2.html  # Restrictions manager
│   └── static/                    # Static assets
│       ├── css/
│       │   ├── style.css          # Main styles
│       │   └── toggle-theme.css   # Dark/light mode styles
│       ├── js/
│       │   ├── main.js            # Core JavaScript
│       │   ├── dashboard.js       # Dashboard functionality
│       │   ├── channel_restriction_v2.js  # Restrictions UI
│       │   └── theme-toggle.js    # Theme switching
│       └── images/                # Logo, favicons
│
└── Data_Files/                    # Configuration
    ├── .env                       # Environment variables
    ├── requirements.txt           # Python dependencies
    └── SQL.txt                    # Database schema
```

---

## 🤝 Support

Need help? Reach out through these channels:

| Platform | Link |
|----------|------|
| 💬 Discord | [Join Support Server](https://discord.gg/NbNNU24HjF) |
| 🐙 GitHub | [@Shabdprakash-Thakkar](https://github.com/Shabdprakash-Thakkar) |
| 📸 Instagram | [@study_time_95](https://www.instagram.com/study_time_95/) |
| 🌐 Website | [shabdprakash-thakkar.online](https://shabdprakash-thakkar.online) |
| 📧 Email | shabdprakash95@gmail.com |

---

## 📜 License

This project is provided for educational and personal use. Feel free to modify and adapt for your own servers.

---

<div align="center">

**Made with ❤️ for Discord communities**

![Discord](https://img.shields.io/badge/Discord-5865F2?style=flat-square&logo=discord&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=flat-square&logo=flask&logoColor=white)

*© 2025 Supporter BOT by Shabdprakash Thakkar*

</div>