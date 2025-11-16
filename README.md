# Supporter BOT

A multi-functional Discord bot designed to automate server management and enhance user engagement. This bot features a comprehensive leveling system, YouTube notifications, automated time-channel updates, and advanced media/link control systems, all managed through intuitive slash commands. It is built to be robust, scalable, and easy for server administrators to configure.

## ✨ Key Features

* **🏆 Advanced Leveling System:** Engage your community by rewarding users with XP for their activity. The system includes automatic role rewards for reaching new levels, a server-wide leaderboard to foster competition, and a dedicated channel for level-up announcements. For seasonal events, administrators can perform a manual or scheduled automatic reset of all user XP and roles.

* **📢 YouTube Notifications:** Automatically announce new video uploads, livestreams, and premieres from your favorite YouTube channels. Features a customizable message with role mentions, a helper command to easily find any channel's ID, and admin tools to seed historical videos or test the channel RSS feed. The bot uses RSS feeds (no API quota required) for reliable monitoring.

* **🚫📝 No-Text Channel Enforcement:** Create dedicated media-only channels where plain text is not allowed. The bot will automatically remove text-only messages and send a temporary notification, guiding users to the correct channel for conversations. A role-based bypass system allows designated members to override this restriction.

* **📝 Text-Only Channel Enforcement:** Create dedicated text-only channels where attachments, embeds, and image links are not allowed. Perfect for discussion channels where you want to prevent media spam while allowing normal conversation.

* **🔗 Advanced Link Control System:** Three-tier link restriction system to maintain channel quality:
  * **No Discord Links**: Blocks Discord server/channel invite links (discord.gg, discord.com/invite) to prevent server promotion while allowing all other links (YouTube, Instagram, etc.)
  * **No Links**: Most restrictive - blocks ALL links silently
  * Role-based bypass system applies to all restrictions

* **⏰ Live Time Channels:** Keep your server's international community synchronized with voice channels that automatically update their names to display the current date, India Standard Time (IST), and Japan Standard Time (JST).

* **🌐 Web Frontend:** Modern Flask-based website showcasing bot features, statistics, and a contact form for support.

* **⚙️ Easy Configuration & Control:** All features are managed through simple slash commands. A dedicated `/g2-show-config` command allows administrators to get a quick overview of all bot settings, while owner-only commands provide full control over the bot's presence in different servers.

---

## 🏆 XP & Leveling System Details

The bot uses a simple, linear progression system where a new level is achieved every **1,000 total XP**. Users earn XP in several ways:

* **Text Messages**: 10 XP per message  
* **Image Messages**: 15 XP per message  
* **Voice Chat**: 4 XP per 60 seconds of activity (capped at 1,500 XP per reset period)

---

## 🤖 Command List

All bot interactions are handled through slash commands available by typing `/` in Discord.

### General Commands (6)

| Command           | Description                                       | Permissions   |
| :---------------- | :------------------------------------------------ | :------------ |
| `/g1-help`        | Shows a list of all available bot commands.       | Everyone      |
| `/g2-show-config` | Displays the current configuration for the server.| Manage Guild  |
| `/g3-serverlist`  | Lists all servers the bot is in.                  | Bot Owner     |
| `/g4-leaveserver` | Forces the bot to leave a server by ID.           | Bot Owner     |
| `/g5-banguild`    | Bans a server and makes the bot leave.            | Bot Owner     |
| `/g6-unbanguild`  | Unbans a server, allowing it to re-invite the bot.| Bot Owner     |

### Leveling Commands (10)

| Command                  | Description                                                       | Permissions   |
| :----------------------- | :---------------------------------------------------------------- | :------------ |
| `/l1-level`              | Checks the current level and XP of yourself or another user.      | Everyone      |
| `/l2-leaderboard`        | Shows the top 10 users on the server leaderboard.                 | Everyone      |
| `/l3-setup-level-reward` | Sets a role reward for reaching a specific level.                 | Manage Roles  |
| `/l4-level-reward-show`  | Views all configured level rewards for the server.                | View Audit Log|
| `/l5-notify-level-msg`   | Sets the channel for level-up notification messages.              | Manage Channels|
| `/l6-set-auto-reset`     | Sets an automatic XP reset schedule (1-365 days).                 | Administrator |
| `/l7-show-auto-reset`    | Shows the current auto-reset configuration for this server.       | Administrator |
| `/l8-stop-auto-reset`    | Disables the automatic XP reset for this server.                  | Administrator |
| `/l9-reset-xp`           | Manually resets all XP/levels and removes reward roles.           | Administrator |
| `/l10-upgrade-all-roles` | Manually syncs roles for all users based on their current level.  | Manage Roles  |

### YouTube Notification Commands (5)

| Command                              | Description                                               | Permissions   |
| :----------------------------------- | :-------------------------------------------------------- | :------------ |
| `/y1-find-youtube-channel-id`        | Finds a channel's ID using its @handle or custom name.    | Everyone      |
| `/y2-setup-youtube-notifications`    | Sets up notifications for a specific YouTube channel.     | Manage Guild  |
| `/y3-disable-youtube-notifications`  | Disables notifications for a configured YouTube channel.  | Manage Guild  |
| `/y4-bulk-seed-all-videos`           | [ADMIN] Seed existing videos from a channel (bulk seed).  | Administrator |
| `/y5-test-rss-feed`                  | [ADMIN] Test the RSS feed for a channel and preview results.| Manage Guild|

### Channel Restriction Commands (11)

| Command                        | Description                                                          | Permissions      |
| :----------------------------- | :------------------------------------------------------------------- | :--------------- |
| `/n1-setup-no-text`            | Restricts a channel to only allow media and links (no plain text).   | Manage Channels  |
| `/n2-remove-no-text`           | Removes the no-text restriction from a channel.                      | Manage Channels  |
| `/n3-bypass-no-text`           | Allows a role to bypass all message restrictions.                    | Manage Roles     |
| `/n4-show-bypass-roles`        | Shows all roles that can bypass restrictions.                        | Manage Roles     |
| `/n5-remove-bypass-role`       | Removes a role's ability to bypass restrictions.                     | Manage Roles     |
| `/n6-no-discord-link`          | Blocks Discord invite links (allows other links).                    | Manage Channels  |
| `/n7-no-links`                 | Blocks ALL links silently (most restrictive).                        | Manage Channels  |
| `/n8-remove-no-discord-link`   | Removes Discord invite link restriction from a channel.              | Manage Channels  |
| `/n9-remove-no-links`          | Removes all link restrictions from a channel.                        | Manage Channels  |
| `/n10-setup-text-only`         | Restricts a channel to only allow plain text (no attachments/embeds).| Manage Channels  |
| `/n11-remove-text-only`        | Removes the text-only restriction from a channel.                    | Manage Channels  |

### Time Channel Commands (1)

| Command                      | Description                                               | Permissions    |
| :--------------------------- | :-------------------------------------------------------- | :------------- |
| `/t1-setup-time-channels`    | Sets up channels for date, India time, and Japan time.    | Manage Channels|

**Total Commands: 33**

---

## 📂 Project Structure

```
Supporter/
│
├── run_production.py          # Main startup script (runs both bot + web frontend)
│
├── Python_Files/              # Discord Bot Code
│   ├── supporter.py           # Main bot file, event handling, command registration
│   ├── level.py               # Leveling system and XP management
│   ├── no_text.py             # Channel restrictions (media-only, text-only, link control)
│   ├── date_and_time.py       # Auto-updating time channels
│   ├── youtube_notification.py # YouTube RSS feed monitoring
│   ├── owner_actions.py       # Owner commands (ban/leave servers)
│   └── help.py                # Help command system
│
├── Flask_Frontend/            # Web Frontend
│   ├── app.py                 # Flask application (routes, API endpoints)
│   ├── templates/             # HTML templates
│   │   ├── base.html          # Base template with navbar/footer
│   │   ├── index.html         # Homepage
│   │   └── contact.html       # Contact page
│   └── static/                # Static files (CSS, JS, images)
│       ├── css/
│       │   └── style.css      # Custom styles
│       ├── js/
│       │   └── main.js        # Frontend JavaScript
│       └── images/
│           └── bot-logo.png   # Bot logo
│
└── Data_Files/                # Configuration & Data
    ├── .env                   # Environment variables (credentials)
    ├── requirements.txt       # Python dependencies
    └── SQL.txt                # PostgreSQL database schema
```

---

## 🚀 Setup and Installation Guide

### Step 1: Prerequisites

Before you begin, you will need:

* Python 3.8 or a newer version installed.
* A Discord Bot application created on the [Discord Developer Portal](https://discord.com/developers/applications).
* A PostgreSQL database (Supabase recommended for free hosting).
* A YouTube Data API Key (optional - only needed for bulk video seeding).

### Step 2: Bot Installation

1. Download or clone the project files to your computer.
2. Create and activate a Python virtual environment (recommended):

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install all required Python libraries:

   ```bash
   pip install -r Data_Files/requirements.txt
   ```

### Step 3: Database Configuration

The bot uses PostgreSQL to store all persistent data. In your database project's SQL Editor, run the complete database setup script from `Data_Files/SQL.txt` to create all required tables.

**Required Tables:**

* `users` - Stores user XP, levels, and voice XP
* `level_roles` - Stores role rewards for levels
* `level_notify_channel` - Stores notification channel configuration
* `last_notified_level` - Tracks last notified level per user
* `bypass_roles` - Stores roles that can bypass restrictions
* `auto_reset` - Stores automatic XP reset configuration
* `youtube_notification_config` - Stores YouTube channel notification settings
* `youtube_notification_logs` - Stores notification history
* `no_text_channels` - Stores media-only channel configurations
* `text_only_channels` - Stores text-only channel configurations
* `no_discord_links_channels` - Stores channels with Discord link restrictions
* `no_links_channels` - Stores channels with all link restrictions
* `time_channel_config` - Stores time channel configurations
* `banned_guilds` - Stores banned server IDs

### Step 4: Server & Domain Configuration

This project contains some hardcoded values (IP addresses, Ports, and Domain names) used for console logging and CORS (Cross-Origin Resource Sharing) security.

Before deploying, you must update these files to match your own server's details:

#### 1. `run_production.py` (Root Directory)
This file controls the startup process and console logs.
*   **Lines 34-36 & 54-56:** Update the `print` statements to show your actual Server IP and Domain.
*   **Line 70:** Update the URL to match your server's address.

```python
# Example of what to look for:
print("📍 Server IP: YOUR_SERVER_IP")     # Change this
print("🔌 Port: 1234")                    # Change this
print("🌍 Domain: https://your-domain.com") # Change this
```

#### 2. `Flask_Frontend/app.py`
This is the web server file. It restricts which domains can access the API.
*   **Line 26 (CORS Configuration):** You **must** change the domain and IP list here, or the frontend will not be able to fetch data from the backend.
*   **Line 93 (Health Check):** Update the domain name string.

```python
# Find this list and update it:
"origins": [
    "https://your-domain.com",       # Change to your domain
    "http://your-server-ip:port",    # Change to your IP
    "http://localhost:1234",         # change to your port
]
```

### Step 5: Running the Bot

Once all the previous steps are completed and your credentials are in place, run the bot:

```bash
python run_production.py
```

The bot will:

1. Connect to your database
2. Initialize all feature managers (leveling, YouTube, time channels, etc.)
3. Start the Discord bot process
4. Start the Flask web frontend on port 9458
5. Display a list of servers it's connected to

**Expected Output:**
```
============================================================
🚀 SUPPORTER BOT - PRODUCTION DEPLOYMENT
============================================================

📦 Server Configuration:
   • Port: 5000
   • Environment: Production

🔄 Starting both Discord Bot and Flask Frontend...

============================================================
✅ BOTH SERVICES STARTED SUCCESSFULLY!
============================================================

🤖 Discord Bot: Running
🌐 Flask Frontend: http://0.0.0.0:5000
```

### Step 6: Inviting the Bot to Your Server

1. Go to Discord Developer Portal → Your Application → OAuth2 → URL Generator
2. Select scopes: `bot` and `applications.commands`
3. Select bot permissions:
   * Manage Roles
   * Manage Channels
   * Send Messages
   * Manage Messages
   * Read Message History
   * Mention Everyone
   * View Channels
   * Connect (for voice state tracking)
4. Copy the generated URL and open it in your browser to invite the bot

---

## 📝 Notes

* All link restrictions delete messages **silently** with no warning.
* Administrators and server owners automatically bypass all restrictions.
* The voice XP cap (1,500 XP) resets when the server's XP is reset (manual or automatic).
* Time channels update every 10 minutes, date channels update daily at midnight IST.
* YouTube notifications check for new content every 15 minutes.
* The bot uses RSS feeds for YouTube monitoring (no API quota limits).
* Auto-seeding prevents notification spam when adding new YouTube channels.

---

## 🐛 Troubleshooting

### Bot not responding to commands
- Verify bot has proper permissions in your server
- Check if bot has "Message Content Intent" enabled in Discord Developer Portal
- Try re-syncing commands: the bot does this automatically on startup

### Database connection errors
- Verify your `DATABASE_URL` is correct in `.env`
- Check if your database is online and accessible
- Ensure all required tables are created from `SQL.txt`

### YouTube notifications not working
- Verify the YouTube Channel ID starts with "UC" and is 24 characters long
- Use `/y5-test-rss-feed` to test the RSS feed
- Check bot has permission to send messages in the notification channel
- Wait at least 15 minutes after setup for the first check

### Level roles not being assigned
- Ensure bot's role is **above** the reward roles in server settings
- Check bot has "Manage Roles" permission
- Use `/l10-upgrade-all-roles` to manually sync all roles

---

## 🤝 Support

For issues, questions, or feature requests:
- Discord Server: [Join here](https://discord.gg/)
- GitHub: [@Shabdprakash-Thakkar](https://github.com/)
- Instagram: [@study_time_95](https://www.instagram.com/)
- Website: [shabdprakash-thakkar.online](https://shabdprakash-thakkar.online)

---

**Made with ❤️ for Discord communities**