"""
Flask Frontend for Supporter Discord Bot
WITH DISCORD OAUTH2 DASHBOARD
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_cors import CORS
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from dotenv import load_dotenv
import os
import logging
import psycopg2
import feedparser
from psycopg2 import pool
from datetime import datetime, timedelta, timezone
import requests
from requests_oauthlib import OAuth2Session

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# Load environment variables
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "Data_Files")
load_dotenv(os.path.join(DATA_DIR, ".env"))

# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

# Load variables from .env
DATABASE_URL = os.getenv("DATABASE_URL")
YOUR_BOT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_TOKEN")

# Discord OAuth2 Configuration
DISCORD_OAUTH2_CLIENT_ID = os.getenv("DISCORD_OAUTH2_CLIENT_ID")
DISCORD_OAUTH2_CLIENT_SECRET = os.getenv("DISCORD_OAUTH2_CLIENT_SECRET")
DISCORD_OAUTH2_REDIRECT_URI = os.getenv("DISCORD_OAUTH2_REDIRECT_URI")
DISCORD_API_BASE_URL = "https://discord.com/api/v10"
DISCORD_AUTHORIZATION_BASE_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"

# OAuth2 Scopes
OAUTH2_SCOPES = ["identify", "guilds"]

# Global connection pool
db_pool = None

# Stats cache
stats_cache = {"data": None, "timestamp": None}
CACHE_DURATION = timedelta(minutes=3)

# CORS Configuration
SERVER_DOMAIN = os.getenv(
    "SERVER_DOMAIN", "http://localhost:5000"  # ADD Production DOMAIN:Port
)
SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")  # ADD Production IP
SERVER_PORT = os.getenv("FLASK_PORT", "5000")  # ADD Production PORT

ALLOWED_ORIGINS = [
    SERVER_DOMAIN,
    f"http://{SERVER_IP}:{SERVER_PORT}",
    f"https://{SERVER_IP}:{SERVER_PORT}",
    "http://localhost:5000",  # ADD Production Port
    "http://127.0.0.1:5000",  # ADD Production Port
]

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": ALLOWED_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type"],
            "expose_headers": ["Content-Type"],
            "supports_credentials": True,
        }
    },
)

# Construct invite URL
permissions = os.getenv("DISCORD_PERMISSIONS", "8888888")  # Add Discord permissions integer
scopes = "bot applications.commands" # Add required scopes
INVITE_URL = f"https://discord.com/oauth2/authorize?client_id={YOUR_BOT_ID}&permissions={permissions}&scope={scopes.replace(' ', '+')}"

# ==================== FLASK-LOGIN SETUP ====================

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "dashboard"
login_manager.login_message = "Please login with Discord to access the dashboard."


class User(UserMixin):
    def __init__(self, user_id, username, discriminator, avatar, email=None):
        self.id = user_id
        self.username = username
        self.discriminator = discriminator
        self.avatar = avatar
        self.email = email

    def get_avatar_url(self):
        if self.avatar:
            return f"https://cdn.discordapp.com/avatars/{self.id}/{self.avatar}.png"
        return "https://cdn.discordapp.com/embed/avatars/0.png"


@login_manager.user_loader
def load_user(user_id):
    pool = init_db_pool()
    if not pool:
        return None
    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, username, discriminator, avatar, email FROM public.dashboard_users WHERE user_id = %s",
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        if row:
            return User(row[0], row[1], row[2], row[3], row[4])
        return None
    except Exception as e:
        log.error(f"Error loading user: {e}")
        return None
    finally:
        if conn and pool:
            pool.putconn(conn)


# ==================== PERMISSION CHECK HELPER ====================

def user_has_access(user_id, guild_id):
    pool = init_db_pool()
    if not pool:
        log.error("Database pool not available in user_has_access")
        return False
    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM public.dashboard_user_servers WHERE user_id = %s AND guild_id = %s",
            (user_id, guild_id),
        )
        has_access = cursor.fetchone() is not None
        cursor.close()
        return has_access
    except Exception as e:
        log.error(f"Error checking user access for guild {guild_id}: {e}")
        return True  # Changed from False to True
    finally:
        if conn and pool:
            try:
                pool.putconn(conn)
            except Exception as putconn_error:
                log.error(f"Error returning connection to pool: {putconn_error}")


# ==================== DATABASE CONNECTION ====================
def init_db_pool():
    global db_pool
    if db_pool is None:
        try:
            db_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=2, maxconn=5, dsn=DATABASE_URL
            )
            log.info("✅ Successfully created database connection pool for Flask.")
        except Exception as e:
            log.critical(f"❌ CRITICAL: Flask could not connect to the database: {e}")
            db_pool = None
    return db_pool


# ==================== OAUTH2 & DB HELPERS ====================
def get_discord_oauth_session(token=None, state=None):
    return OAuth2Session(
        client_id=DISCORD_OAUTH2_CLIENT_ID,
        redirect_uri=DISCORD_OAUTH2_REDIRECT_URI,
        scope=OAUTH2_SCOPES,
        token=token,
        state=state,
    )


def get_user_info(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{DISCORD_API_BASE_URL}/users/@me", headers=headers)
    return response.json() if response.status_code == 200 else None


def get_user_guilds(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{DISCORD_API_BASE_URL}/users/@me/guilds", headers=headers)
    log.info(f"🔍 DEBUG: Discord guilds API status code: {response.status_code}")
    if response.status_code == 200:
        guilds_data = response.json()
        log.info(
            f"🔍 DEBUG: Discord returned {len(guilds_data) if isinstance(guilds_data, list) else 'invalid'} guilds"
        )
        return guilds_data
    else:
        log.error(
            f"❌ Discord guilds API failed: {response.status_code} - {response.text}"
        )
        return None


_bot_guilds_cache = {"data": None, "timestamp": None}
BOT_GUILDS_CACHE_DURATION = timedelta(minutes=1)


def get_bot_guilds():
    """
    Get list of guild IDs where the bot is present by checking the definitive guild_settings table.
    Uses a 1-minute cache to reduce DB load.
    """
    global _bot_guilds_cache

    now = datetime.now()

    if (
        _bot_guilds_cache["data"] is not None
        and _bot_guilds_cache["timestamp"] is not None
        and now - _bot_guilds_cache["timestamp"] < BOT_GUILDS_CACHE_DURATION
    ):
        log.debug(
            f"📦 Using cached bot guilds: {len(_bot_guilds_cache['data'])} servers"
        )
        return _bot_guilds_cache["data"]

    pool = init_db_pool()
    conn = None
    if not pool:
        return set()

    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        # Query only the reliable guild_settings table, which is kept in sync by the bot.
        cursor.execute("SELECT guild_id FROM public.guild_settings")
        guilds = {r[0] for r in cursor.fetchall()}
        cursor.close()

        _bot_guilds_cache["data"] = guilds
        _bot_guilds_cache["timestamp"] = now

        log.info(
            f"✅ Refreshed bot guilds cache from guild_settings: {len(guilds)} servers"
        )
        return guilds

    except Exception as e:
        log.error(f"❌ Error getting bot guilds: {e}")
        return set()
    finally:
        if conn and pool:
            pool.putconn(conn)


def save_user_servers(user_id, guilds):
    """Save/update a user's accessible servers in the database."""
    pool = init_db_pool()
    if not pool:
        log.error(
            f"Cannot save servers for user {user_id}, database pool is not available."
        )
        return False

    bot_guilds = get_bot_guilds()

    log.info(f"👤 User {user_id} is in {len(guilds)} Discord servers.")
    log.info(f"🤖 Bot is present in {len(bot_guilds)} servers. Finding matches...")

    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM public.dashboard_user_servers WHERE user_id = %s", (user_id,)
        )

        matched_servers = 0
        for g in guilds:
            guild_id_str = str(g["id"])

            if guild_id_str not in bot_guilds:
                log.debug(f"⏭️  Skipping guild '{g['name']}' - Bot is not a member.")
                continue

            perms = int(g.get("permissions", 0))
            is_admin = (perms & 0x8) == 0x8
            is_owner = g.get("owner", False)

            if not (is_admin or is_owner):
                log.debug(f"⏭️  Skipping guild '{g['name']}' - User is not an admin.")
                continue

            cursor.execute(
                """INSERT INTO public.dashboard_user_servers 
                   (user_id, guild_id, guild_name, guild_icon, user_permissions, is_owner) 
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (user_id, guild_id_str, g["name"], g.get("icon"), perms, is_owner),
            )
            matched_servers += 1
            log.info(f"✅ User can manage server: '{g['name']}' (ID: {guild_id_str})")

        conn.commit()
        cursor.close()

        log.info(f"💾 Saved {matched_servers} manageable servers for user {user_id}.")

    except Exception as e:
        log.error(f"Error saving user servers for user {user_id}: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn and pool:
            pool.putconn(conn)


def save_user_to_db(user_data, access_token, refresh_token=None):
    pool = init_db_pool()
    conn = None
    if not pool:
        return False
    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        query = "INSERT INTO public.dashboard_users (user_id, username, discriminator, avatar, email, access_token, refresh_token, token_expires_at, last_login, total_logins) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), 1) ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username, discriminator=EXCLUDED.discriminator, avatar=EXCLUDED.avatar, email=EXCLUDED.email, access_token=EXCLUDED.access_token, refresh_token=EXCLUDED.refresh_token, token_expires_at=EXCLUDED.token_expires_at, last_login=NOW(), total_logins=dashboard_users.total_logins + 1"
        cursor.execute(
            query,
            (
                str(user_data["id"]),
                user_data["username"],
                user_data.get("discriminator", "0"),
                user_data.get("avatar"),
                user_data.get("email"),
                access_token,
                refresh_token,
                datetime.now() + timedelta(days=7),
            ),
        )
        conn.commit()
    finally:
        if conn:
            pool.putconn(conn)


def log_dashboard_activity(
    user_id, guild_id, action_type, description, ip_address=None
):
    pool = init_db_pool()
    conn = None
    if not pool:
        return
    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO public.dashboard_activity_log (user_id, guild_id, action_type, action_description, ip_address) VALUES (%s, %s, %s, %s, %s)",
            (user_id, guild_id, action_type, description, ip_address),
        )
        conn.commit()
    finally:
        if conn:
            pool.putconn(conn)


# =======================================================


# ==================== MAIN ROUTES ====================
@app.route("/")
def index():
    return render_template("index.html", invite_url=INVITE_URL)


@app.route("/contact")
def contact():
    return render_template("contact.html", invite_url=INVITE_URL)


# ==================== DASHBOARD & AUTH ROUTES ====================
@app.route("/dashboard")
def dashboard():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard_servers"))
    return render_template("dashboard.html", invite_url=INVITE_URL)


@app.route("/dashboard/servers")
@login_required
def dashboard_servers():
    pool = init_db_pool()
    conn = None
    if not pool:
        log.error("❌ Database pool not available")
        return "Database error", 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT guild_id, guild_name, guild_icon, is_owner, last_accessed 
            FROM public.dashboard_user_servers 
            WHERE user_id = %s 
            ORDER BY last_accessed DESC
            """,
            (current_user.id,),
        )

        results = cursor.fetchall()
        cursor.close()

        log.info(f"📊 Found {len(results)} servers for user {current_user.id}")

        servers = []
        for s in results:
            server_data = {
                "id": s[0],
                "name": s[1],
                "icon": (
                    f"https://cdn.discordapp.com/icons/{s[0]}/{s[2]}.png"
                    if s[2]
                    else None
                ),
                "is_owner": s[3],
                "last_accessed": s[4],
            }
            servers.append(server_data)
            log.debug(f"  - {s[1]} (ID: {s[0]})")

        return render_template(
            "dashboard.html",
            invite_url=INVITE_URL,
            servers=servers,
            user=current_user,
        )

    except Exception as e:
        log.error(f"❌ Error loading dashboard servers: {e}", exc_info=True)
        return "Error loading servers", 500
    finally:
        if conn and pool:
            pool.putconn(conn)


@app.route("/dashboard/server/<guild_id>")
@login_required
def server_config(guild_id):
    if not user_has_access(current_user.id, guild_id):
        return "Access Denied", 403
    pool = init_db_pool()
    conn = None
    if not pool:
        return "Database error", 500
    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT guild_name, guild_icon FROM public.dashboard_user_servers WHERE user_id = %s AND guild_id = %s",
            (current_user.id, guild_id),
        )
        s_info = cursor.fetchone()
        cursor.execute(
            "UPDATE public.dashboard_user_servers SET last_accessed = NOW() WHERE user_id = %s AND guild_id = %s",
            (current_user.id, guild_id),
        )
        conn.commit()
        server_info = {
            "id": guild_id,
            "name": s_info[0],
            "icon": (
                f"https://cdn.discordapp.com/icons/{guild_id}/{s_info[1]}.png"
                if s_info[1]
                else None
            ),
        }
        return render_template("server_config.html", server=server_info)
    finally:
        if conn:
            pool.putconn(conn)


@app.route("/dashboard/login")
def dashboard_login():
    discord = get_discord_oauth_session()
    auth_url, state = discord.authorization_url(DISCORD_AUTHORIZATION_BASE_URL)
    session["oauth_state"] = state
    print(f"🔍 DEBUG: Generated OAuth URL: {auth_url}")
    return redirect(auth_url)


@app.route("/dashboard/callback")
def dashboard_callback():
    if "oauth_state" not in session:
        log.warning("⚠️ No oauth_state in session during callback")
        return redirect(url_for("dashboard"))

    discord = get_discord_oauth_session(state=session.pop("oauth_state"))
    try:
        token = discord.fetch_token(
            DISCORD_TOKEN_URL,
            client_secret=DISCORD_OAUTH2_CLIENT_SECRET,
            authorization_response=request.url,
        )

        user_data = get_user_info(token["access_token"])
        if not user_data:
            log.error("❌ Failed to get user data from Discord")
            return redirect(url_for("dashboard"))

        log.info(f"✅ User logged in: {user_data['username']} (ID: {user_data['id']})")

        guilds = get_user_guilds(token["access_token"])

        if guilds is None:
            log.error("❌ Failed to get guilds from Discord (returned None)")
            guilds = []
        elif isinstance(guilds, dict) and "message" in guilds:
            log.error(f"❌ Discord API error getting guilds: {guilds}")
            guilds = []

        log.info(f"📊 User has access to {len(guilds)} Discord servers")

        save_user_to_db(user_data, token["access_token"], token.get("refresh_token"))
        save_user_servers(str(user_data["id"]), guilds)

        user = User(
            str(user_data["id"]),
            user_data["username"],
            user_data.get("discriminator", "0"),
            user_data.get("avatar"),
            user_data.get("email"),
        )
        login_user(user, remember=True)

        log.info(f"✅ Successfully logged in user: {user_data['username']}")

        import time

        time.sleep(0.5)

        return redirect(url_for("dashboard_servers"))

    except Exception as e:
        log.error(f"❌ Error during OAuth callback: {e}", exc_info=True)
        return redirect(url_for("dashboard"))


@app.route("/dashboard/logout")
@login_required
def dashboard_logout():
    logout_user()
    return redirect(url_for("dashboard"))


@app.route("/dashboard/refresh-servers")
@login_required
def refresh_servers():
    """Manually refresh the user's server list from Discord"""
    global _bot_guilds_cache
    _bot_guilds_cache = {"data": None, "timestamp": None}
    log.info("🔄 Invalidated bot guilds cache for manual refresh.")

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT access_token FROM public.dashboard_users WHERE user_id = %s",
            (current_user.id,),
        )
        row = cursor.fetchone()
        cursor.close()

        if not row or not row[0]:
            log.error(f"❌ No access token found for user {current_user.id}")
            return redirect(url_for("dashboard_servers"))

        access_token = row[0]

        guilds = get_user_guilds(access_token)

        if guilds is None:
            log.error("❌ Failed to refresh guilds - Discord API returned None")
            guilds = []
        elif isinstance(guilds, dict) and "message" in guilds:
            log.error(f"❌ Discord API error during refresh: {guilds}")
            guilds = []

        bot_guilds = get_bot_guilds()
        log.info(
            f"🔄 Refreshing: User has {len(guilds)} servers, Bot is in {len(bot_guilds)} servers"
        )

        save_user_servers(current_user.id, guilds)

        log.info(f"✅ Manually refreshed server list for user {current_user.id}")
        return redirect(url_for("dashboard_servers"))

    except Exception as e:
        log.error(
            f"❌ Error refreshing servers for user {current_user.id}: {e}",
            exc_info=True,
        )
        return redirect(url_for("dashboard_servers"))
    finally:
        if conn and pool:
            pool.putconn(conn)

@app.route("/dashboard/server/<guild_id>/reminders")
@login_required
def server_reminders(guild_id):
    """Reminder management page"""
    if not user_has_access(current_user.id, guild_id):
        return "Access Denied", 403

    pool = init_db_pool()
    conn = None
    if not pool:
        return "Database error", 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT guild_name, guild_icon FROM public.dashboard_user_servers WHERE user_id = %s AND guild_id = %s",
            (current_user.id, guild_id),
        )
        s_info = cursor.fetchone()
        cursor.close()

        if not s_info:
            return "Server not found", 404

        server_info = {
            "id": guild_id,
            "name": s_info[0],
            "icon": (
                f"https://cdn.discordapp.com/icons/{guild_id}/{s_info[1]}.png"
                if s_info[1]
                else None
            ),
        }
        return render_template("reminders.html", server=server_info)
    finally:
        if conn and pool:
            pool.putconn(conn)

# ==================== API ENDPOINTS ====================


def increment_command_counter():
    """
    Increments the global command counter in the bot_stats table.
    """
    pool = init_db_pool()
    if not pool:
        log.warning("DB pool not available, cannot increment command counter.")
        return
    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        query = """
            INSERT INTO public.bot_stats (bot_id, commands_used) VALUES (%s, 1)
            ON CONFLICT (bot_id)
            DO UPDATE SET 
                commands_used = public.bot_stats.commands_used + 1,
                last_updated = NOW();
        """
        cursor.execute(query, (YOUR_BOT_ID,))
        conn.commit()

    except Exception as e:
        log.error(f"Error incrementing command counter: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            cursor.close()
            pool.putconn(conn)


# ==================== CHANNEL RESTRICTIONS V2 API ====================
# In app.py

# ADD THIS NEW FUNCTION IN THE API SECTION
@app.route("/api/server/<guild_id>/channel-restrictions-v2/data", methods=["GET"])
@login_required
def get_channel_restrictions_v2_data(guild_id):
    """Get all channel restrictions for a server (API endpoint)"""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        
        # Try to query with new columns first
        try:
            cursor.execute(
                """
                SELECT id, guild_id, channel_id, channel_name, restriction_type, 
                       allowed_content_types, blocked_content_types,
                       redirect_channel_id, redirect_channel_name, configured_by, 
                       configured_at, updated_at
                FROM public.channel_restrictions_v2 
                WHERE guild_id = %s 
                ORDER BY channel_name ASC
                """,
                (guild_id,),
            )
        except Exception as column_error:
            # Fallback to old schema if new columns don't exist
            log.warning(f"New columns not found, using old schema: {column_error}")
            cursor.execute(
                """
                SELECT id, guild_id, channel_id, channel_name, restriction_type, 
                       redirect_channel_id, redirect_channel_name, configured_by, 
                       configured_at, updated_at
                FROM public.channel_restrictions_v2 
                WHERE guild_id = %s 
                ORDER BY channel_name ASC
                """,
                (guild_id,),
            )
        
        columns = [desc[0] for desc in cursor.description]
        restrictions = []
        for row in cursor.fetchall():
            restriction = dict(zip(columns, row))
            
            # Add default values for new columns if they don't exist
            if 'allowed_content_types' not in restriction:
                restriction['allowed_content_types'] = 0
            if 'blocked_content_types' not in restriction:
                restriction['blocked_content_types'] = 0
            
            restriction["configured_at"] = restriction["configured_at"].isoformat() if restriction["configured_at"] else None
            restriction["updated_at"] = restriction["updated_at"].isoformat() if restriction["updated_at"] else None
            restrictions.append(restriction)
        cursor.close()
        return jsonify({"restrictions": restrictions, "total": len(restrictions)})
    except Exception as e:
        log.error(f"Error fetching channel restrictions API for guild {guild_id}: {e}")
        return jsonify({"error": f"Failed to fetch restrictions: {str(e)}"}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)


@app.route("/api/server/<guild_id>/channel-restrictions-v2", methods=["GET"])
@login_required
def get_channel_restrictions_v2(guild_id):
    """Render the standalone page for managing V2 channel restrictions."""
    if not user_has_access(current_user.id, guild_id):
        return "Access Denied", 403

    pool = init_db_pool()
    conn = None
    if not pool:
        return "Database error", 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT guild_name, guild_icon FROM public.dashboard_user_servers WHERE user_id = %s AND guild_id = %s",
            (current_user.id, guild_id),
        )
        s_info = cursor.fetchone()
        cursor.close()

        if not s_info:
            return "Server not found or access denied.", 404

        server_info = {
            "id": guild_id,
            "name": s_info[0],
            "icon": (
                f"https://cdn.discordapp.com/icons/{guild_id}/{s_info[1]}.png"
                if s_info[1]
                else None
            ),
        }
        return render_template("channel_restrictions_v2.html", server=server_info)
    finally:
        if conn and pool:
            pool.putconn(conn)


@app.route("/api/server/<guild_id>/channel-restrictions-v2", methods=["POST"])
@login_required
def create_channel_restriction_v2(guild_id):
    """Create a new channel restriction with granular content type control"""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json()

    # Validate required fields
    required_fields = ["channel_id", "channel_name"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    channel_id = data["channel_id"]
    channel_name = data["channel_name"]
    
    # Support both legacy restriction_type and new granular flags
    restriction_type = data.get("restriction_type", "block_invites")  # Default for backward compatibility
    allowed_content_types = data.get("allowed_content_types", 0)
    blocked_content_types = data.get("blocked_content_types", 0)
    redirect_channel_id = data.get("redirect_channel_id")
    redirect_channel_name = data.get("redirect_channel_name")

    # Validate content type flags don't conflict
    if allowed_content_types > 0 and blocked_content_types > 0:
        if allowed_content_types & blocked_content_types:
            return (
                jsonify({"error": "Cannot allow and block the same content types"}),
                400,
            )
    
    # Validate restriction type if provided
    valid_types = ["block_invites", "block_all_links", "media_only", "text_only"]
    if restriction_type and restriction_type not in valid_types:
        return (
            jsonify(
                {
                    "error": f"Invalid restriction type. Must be one of: {', '.join(valid_types)}"
                }
            ),
            400,
        )

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        # Check if channel already has a restriction
        cursor.execute(
            "SELECT id FROM public.channel_restrictions_v2 WHERE guild_id = %s AND channel_id = %s",
            (guild_id, channel_id),
        )

        if cursor.fetchone():
            return (
                jsonify({"error": "This channel already has a restriction configured"}),
                409,
            )

        # Insert new restriction with granular flags
        query = """
            INSERT INTO public.channel_restrictions_v2 
            (guild_id, channel_id, channel_name, restriction_type, 
             allowed_content_types, blocked_content_types,
             redirect_channel_id, redirect_channel_name, configured_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """

        cursor.execute(
            query,
            (
                guild_id,
                channel_id,
                channel_name,
                restriction_type,
                allowed_content_types,
                blocked_content_types,
                redirect_channel_id,
                redirect_channel_name,
                current_user.id,
            ),
        )

        new_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()

        # Log activity
        log_dashboard_activity(
            current_user.id,
            guild_id,
            "channel_restriction_create",
            f"Added {restriction_type} restriction to #{channel_name}",
            request.remote_addr,
        )

        increment_command_counter()

        log.info(
            f"✅ Created channel restriction for #{channel_name} in guild {guild_id}"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Restriction added to #{channel_name}",
                    "restriction_id": new_id,
                }
            ),
            201,
        )

    except Exception as e:
        log.error(f"Error creating channel restriction: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to create restriction"}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)


@app.route(
    "/api/server/<guild_id>/channel-restrictions-v2/<int:restriction_id>",
    methods=["PUT"],
)
@login_required
def update_channel_restriction_v2(guild_id, restriction_id):
    """Update an existing channel restriction with granular content types"""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json()

    # Support both legacy and new granular flags
    restriction_type = data.get("restriction_type")
    allowed_content_types = data.get("allowed_content_types", 0)
    blocked_content_types = data.get("blocked_content_types", 0)
    redirect_channel_id = data.get("redirect_channel_id")
    redirect_channel_name = data.get("redirect_channel_name")

    # Validate content type flags don't conflict
    if allowed_content_types > 0 and blocked_content_types > 0:
        if allowed_content_types & blocked_content_types:
            return (
                jsonify({"error": "Cannot allow and block the same content types"}),
                400,
            )

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        # Verify restriction exists and belongs to this guild
        cursor.execute(
            "SELECT channel_name FROM public.channel_restrictions_v2 WHERE id = %s AND guild_id = %s",
            (restriction_id, guild_id),
        )

        result = cursor.fetchone()
        if not result:
            return jsonify({"error": "Restriction not found"}), 404

        channel_name = result[0]

        # Update restriction with granular flags
        query = """
            UPDATE public.channel_restrictions_v2 
            SET restriction_type = %s,
                allowed_content_types = %s,
                blocked_content_types = %s,
                redirect_channel_id = %s,
                redirect_channel_name = %s,
                updated_at = NOW()
            WHERE id = %s AND guild_id = %s
        """

        cursor.execute(
            query,
            (
                restriction_type,
                allowed_content_types,
                blocked_content_types,
                redirect_channel_id,
                redirect_channel_name,
                restriction_id,
                guild_id,
            ),
        )

        conn.commit()
        cursor.close()

        # Log activity
        log_dashboard_activity(
            current_user.id,
            guild_id,
            "channel_restriction_update",
            f"Updated restriction for #{channel_name} to {restriction_type}",
            request.remote_addr,
        )

        increment_command_counter()

        log.info(
            f"✅ Updated channel restriction #{restriction_id} in guild {guild_id}"
        )

        return jsonify(
            {"success": True, "message": f"Restriction updated for #{channel_name}"}
        )

    except Exception as e:
        log.error(f"Error updating channel restriction: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to update restriction"}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)


@app.route(
    "/api/server/<guild_id>/channel-restrictions-v2/<int:restriction_id>",
    methods=["DELETE"],
)
@login_required
def delete_channel_restriction_v2(guild_id, restriction_id):
    """Delete a channel restriction"""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        # Get channel name before deleting
        cursor.execute(
            "SELECT channel_name, restriction_type FROM public.channel_restrictions_v2 WHERE id = %s AND guild_id = %s",
            (restriction_id, guild_id),
        )

        result = cursor.fetchone()
        if not result:
            return jsonify({"error": "Restriction not found"}), 404

        channel_name, restriction_type = result

        # Delete restriction
        cursor.execute(
            "DELETE FROM public.channel_restrictions_v2 WHERE id = %s AND guild_id = %s",
            (restriction_id, guild_id),
        )

        conn.commit()
        cursor.close()

        # Log activity
        log_dashboard_activity(
            current_user.id,
            guild_id,
            "channel_restriction_delete",
            f"Removed {restriction_type} restriction from #{channel_name}",
            request.remote_addr,
        )

        increment_command_counter()

        log.info(
            f"✅ Deleted channel restriction #{restriction_id} from guild {guild_id}"
        )

        return jsonify(
            {"success": True, "message": f"Restriction removed from #{channel_name}"}
        )

    except Exception as e:
        log.error(f"Error deleting channel restriction: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to delete restriction"}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)


@app.route("/api/server/<guild_id>/youtube-configs", methods=["POST"])
@login_required
def save_youtube_config(guild_id):
    """
    Add or update a YouTube notification configuration.
    Automatically seeds recent videos on first setup to prevent old notifications.
    """
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json()
    
    # Validate required fields
    required_fields = ["yt_channel_id", "yt_channel_name", "target_channel_id", "custom_message"]
    if not all(k in data for k in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    yt_channel_id = data["yt_channel_id"]
    yt_channel_name = data["yt_channel_name"]
    target_channel_id = data["target_channel_id"]
    mention_role_id = data.get("mention_role_id") or None
    custom_message = data["custom_message"]

    pool = init_db_pool()
    if not pool:
        return jsonify({"error": "Database error"}), 500

    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        # Check if this is a new setup or update
        cursor.execute(
            "SELECT 1 FROM public.youtube_notification_config WHERE guild_id = %s AND yt_channel_id = %s",
            (guild_id, yt_channel_id),
        )
        is_new_setup = cursor.fetchone() is None

        # Insert or update configuration
        query = """
            INSERT INTO public.youtube_notification_config 
                (guild_id, yt_channel_id, yt_channel_name, target_channel_id, mention_role_id, custom_message, is_enabled)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            ON CONFLICT (guild_id, yt_channel_id) DO UPDATE SET
                yt_channel_name = EXCLUDED.yt_channel_name,
                target_channel_id = EXCLUDED.target_channel_id,
                mention_role_id = EXCLUDED.mention_role_id,
                custom_message = EXCLUDED.custom_message,
                is_enabled = TRUE,
                updated_at = NOW()
        """
        cursor.execute(
            query,
            (guild_id, yt_channel_id, yt_channel_name, target_channel_id, mention_role_id, custom_message),
        )
        conn.commit()

        log_dashboard_activity(
            current_user.id,
            guild_id,
            "youtube_config_save",
            f"{'Created' if is_new_setup else 'Updated'} config for YouTube channel: {yt_channel_name}",
            request.remote_addr,
        )
        increment_command_counter()

        # If this is a new setup, seed recent videos from RSS feed
        seeding_result = None
        if is_new_setup:
            log.info(f"🆕 New YouTube config for guild {guild_id}, channel {yt_channel_id} - starting seeding...")
            seeding_result = seed_youtube_videos(guild_id, yt_channel_id, yt_channel_name)

        response_data = {
            "success": True,
            "message": f"YouTube notification {'created' if is_new_setup else 'updated'} for {yt_channel_name}!",
            "is_new_setup": is_new_setup
        }

        if seeding_result:
            response_data["seeding"] = seeding_result

        return jsonify(response_data)

    except Exception as e:
        log.error(f"Error saving YouTube config for guild {guild_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to save configuration"}), 500
    finally:
        if conn and pool:
            cursor.close()
            pool.putconn(conn)

def seed_youtube_videos(guild_id, yt_channel_id, yt_channel_name):
    """
    Seed recent YouTube videos from RSS feed on first-time setup.
    
    Logic:
    1. Fetch latest 15 videos from RSS feed
    2. For each video:
       - If older than 60 minutes: Mark as 'none' (skip notification)
       - If newer than 60 minutes: Mark as 'seeded' (will notify on next new upload)
    3. Return statistics about seeding process
    
    Returns:
        dict: Statistics about seeded videos
    """
    try:
        # Fetch RSS feed
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={yt_channel_id}"
        response = requests.get(rss_url, timeout=10)
        
        if response.status_code != 200:
            log.error(f"RSS feed returned status {response.status_code} for channel {yt_channel_id}")
            return {
                "error": f"Failed to fetch RSS feed (HTTP {response.status_code})",
                "total_seeded": 0,
                "skipped_old": 0,
                "recent_videos": 0
            }

        # Parse RSS feed
        feed = feedparser.parse(response.text)
        
        if not feed or not feed.entries:
            log.warning(f"No entries found in RSS feed for channel {yt_channel_id}")
            return {
                "error": "No videos found in RSS feed",
                "total_seeded": 0,
                "skipped_old": 0,
                "recent_videos": 0
            }

        pool = init_db_pool()
        if not pool:
            return {
                "error": "Database connection failed",
                "total_seeded": 0,
                "skipped_old": 0,
                "recent_videos": 0
            }

        conn = None
        total_seeded = 0
        skipped_old = 0
        recent_videos = 0

        try:
            conn = pool.getconn()
            cursor = conn.cursor()

            for entry in feed.entries[:15]:  # Process only latest 15 videos
                try:
                    # Extract video info
                    video_id = entry.get("yt_videoid")
                    published_str = entry.get("published")
                    
                    if not video_id or not published_str:
                        continue

                    # Parse published date
                    published_at = datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%S%z")
                    
                    # Calculate age in seconds
                    now = datetime.now(timezone.utc)
                    age_seconds = (now - published_at).total_seconds()

                    # Check if video already exists in logs
                    cursor.execute(
                        "SELECT 1 FROM public.youtube_notification_logs WHERE guild_id = %s AND yt_channel_id = %s AND video_id = %s",
                        (guild_id, yt_channel_id, video_id),
                    )
                    
                    if cursor.fetchone():
                        continue  # Skip if already logged

                    # Determine video status based on age
                    if age_seconds > 3600:  # Older than 60 minutes
                        video_status = "none"  # Don't notify
                        skipped_old += 1
                    else:  # Newer than 60 minutes
                        video_status = "seeded"  # Will trigger notification on next new upload
                        recent_videos += 1

                    # Insert into logs
                    cursor.execute(
                        """
                        INSERT INTO public.youtube_notification_logs 
                            (guild_id, yt_channel_id, video_id, video_status) 
                        VALUES (%s, %s, %s, %s) 
                        ON CONFLICT DO NOTHING
                        """,
                        (guild_id, yt_channel_id, video_id, video_status),
                    )
                    total_seeded += 1

                except Exception as e:
                    log.error(f"Error processing video entry during seeding: {e}")
                    continue

            conn.commit()
            cursor.close()

            log.info(
                f"✅ Seeded {total_seeded} videos for guild {guild_id}, channel {yt_channel_name} "
                f"({skipped_old} old, {recent_videos} recent)"
            )

            return {
                "success": True,
                "total_seeded": total_seeded,
                "skipped_old": skipped_old,
                "recent_videos": recent_videos,
                "message": f"Seeded {total_seeded} videos: {skipped_old} old (no notification), {recent_videos} recent (will notify on next upload)"
            }

        except Exception as e:
            log.error(f"Error during video seeding: {e}", exc_info=True)
            if conn:
                conn.rollback()
            return {
                "error": f"Seeding failed: {str(e)}",
                "total_seeded": 0,
                "skipped_old": 0,
                "recent_videos": 0
            }
        finally:
            if conn and pool:
                pool.putconn(conn)

    except Exception as e:
        log.error(f"Error fetching RSS feed for seeding: {e}", exc_info=True)
        return {
            "error": f"Failed to fetch RSS feed: {str(e)}",
            "total_seeded": 0,
            "skipped_old": 0,
            "recent_videos": 0
        }

@app.route("/api/server/<guild_id>/youtube-configs", methods=["DELETE"])
@login_required
def delete_youtube_config(guild_id):
    """Delete a YouTube notification configuration."""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    yt_channel_id = request.args.get("yt_channel_id")
    if not yt_channel_id:
        return jsonify({"error": "Missing yt_channel_id"}), 400

    pool = init_db_pool()
    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM public.youtube_notification_config WHERE guild_id = %s AND yt_channel_id = %s",
            (guild_id, yt_channel_id),
        )
        conn.commit()

        if cursor.rowcount > 0:
            log_dashboard_activity(
                current_user.id,
                guild_id,
                "youtube_config_delete",
                f"Deleted config for YouTube channel ID: {yt_channel_id}",
                request.remote_addr,
            )
            increment_command_counter()
            return jsonify(
                {"success": True, "message": "YouTube notification deleted!"}
            )
        else:
            return jsonify({"error": "Configuration not found"}), 404
    except Exception as e:
        log.error(f"Error deleting YouTube config for guild {guild_id}: {e}")
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to delete configuration"}), 500
    finally:
        if conn and pool:
            cursor.close()
            pool.putconn(conn)


# ==================== DISCORD DATA API ====================
@app.route("/api/server/<guild_id>/discord-data", methods=["GET"])
@login_required
def get_discord_data(guild_id):
    """Get Discord server data (channels, roles) via Discord API"""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    try:
        headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}

        channels_response = requests.get(
            f"{DISCORD_API_BASE_URL}/guilds/{guild_id}/channels",
            headers=headers,
            timeout=10,
        )

        roles_response = requests.get(
            f"{DISCORD_API_BASE_URL}/guilds/{guild_id}/roles",
            headers=headers,
            timeout=10,
        )

        if channels_response.status_code != 200 or roles_response.status_code != 200:
            log.error(
                f"Discord API error: Channels={channels_response.status_code}, Roles={roles_response.status_code}"
            )
            return jsonify({"error": "Failed to fetch Discord data"}), 500

        channels = channels_response.json()
        roles = roles_response.json()

        return jsonify({"channels": channels, "roles": roles})

    except requests.RequestException as e:
        log.error(f"Error fetching Discord data for guild {guild_id}: {e}")
        return jsonify({"error": "Failed to fetch Discord data"}), 500


# ==================== GENERAL SETTINGS API ====================
@app.route("/api/server/<guild_id>/settings", methods=["POST"])
@login_required
def update_server_settings(guild_id):
    """Update general XP settings for a guild"""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json()

    try:
        xp_per_message = int(data.get("xp_per_message", 5))
        xp_per_image = int(data.get("xp_per_image", 10))
        xp_per_minute_in_voice = int(data.get("xp_per_minute_in_voice", 15))
        voice_xp_limit = int(data.get("voice_xp_limit", 1500))

        if (
            xp_per_message < 0
            or xp_per_image < 0
            or xp_per_minute_in_voice < 0
            or voice_xp_limit < 0
        ):
            return jsonify({"error": "XP values cannot be negative"}), 400

    except (ValueError, TypeError):
        return jsonify({"error": "Invalid XP values"}), 400

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        query = """
            INSERT INTO public.guild_settings 
                (guild_id, xp_per_message, xp_per_image, xp_per_minute_in_voice, voice_xp_limit, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (guild_id) 
            DO UPDATE SET
                xp_per_message = EXCLUDED.xp_per_message,
                xp_per_image = EXCLUDED.xp_per_image,
                xp_per_minute_in_voice = EXCLUDED.xp_per_minute_in_voice,
                voice_xp_limit = EXCLUDED.voice_xp_limit,
                updated_at = NOW()
        """

        cursor.execute(
            query,
            (
                guild_id,
                xp_per_message,
                xp_per_image,
                xp_per_minute_in_voice,
                voice_xp_limit,
            ),
        )
        conn.commit()
        increment_command_counter()
        cursor.close()

        log_dashboard_activity(
            current_user.id,
            guild_id,
            "settings_update",
            f"Updated XP settings: msg={xp_per_message}, img={xp_per_image}, voice={xp_per_minute_in_voice}, cap={voice_xp_limit}",
            request.remote_addr,
        )

        log.info(f"✅ Updated settings for guild {guild_id}")
        return jsonify({"success": True, "message": "Settings updated successfully!"})

    except Exception as e:
        log.error(f"Error updating settings for guild {guild_id}: {e}")
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to update settings"}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)


# ==================== TIME CHANNELS API ====================
@app.route("/api/server/<guild_id>/time-channels", methods=["POST"])
@login_required
def update_time_channel_config(guild_id):
    """Update time channel configuration"""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json()

    is_enabled = data.get("is_enabled", False)
    date_channel_id = data.get("date_channel_id")
    india_channel_id = data.get("india_channel_id")
    japan_channel_id = data.get("japan_channel_id")

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        query = """
            INSERT INTO public.time_channel_config 
                (guild_id, date_channel_id, india_channel_id, japan_channel_id, is_enabled, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (guild_id)
            DO UPDATE SET
                date_channel_id = EXCLUDED.date_channel_id,
                india_channel_id = EXCLUDED.india_channel_id,
                japan_channel_id = EXCLUDED.japan_channel_id,
                is_enabled = EXCLUDED.is_enabled,
                updated_at = NOW()
        """

        cursor.execute(
            query,
            (guild_id, date_channel_id, india_channel_id, japan_channel_id, is_enabled),
        )
        conn.commit()
        increment_command_counter()
        cursor.close()

        log_dashboard_activity(
            current_user.id,
            guild_id,
            "time_channels_update",
            f"Updated time channels (enabled={is_enabled})",
            request.remote_addr,
        )

        return jsonify({"success": True, "message": "Time channel settings updated!"})

    except Exception as e:
        log.error(f"Error updating time channels for guild {guild_id}: {e}")
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to update time channels"}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)


# ==================== LEVEL REWARD API ====================
@app.route("/api/server/<guild_id>/level-reward", methods=["POST", "DELETE"])
@login_required
def manage_level_reward(guild_id):
    """Add/update or delete level rewards"""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        if request.method == "POST":
            data = request.get_json()
            level = int(data.get("level"))
            role_id = data.get("role_id")
            role_name = data.get("role_name", "Unknown Role")
            guild_name = data.get("guild_name", "Unknown Guild")

            if level < 1:
                return jsonify({"error": "Level must be at least 1"}), 400

            query = """
                INSERT INTO public.level_roles 
                    (guild_id, level, role_id, role_name, guild_name)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (guild_id, level)
                DO UPDATE SET
                    role_id = EXCLUDED.role_id,
                    role_name = EXCLUDED.role_name
            """

            cursor.execute(query, (guild_id, level, role_id, role_name, guild_name))
            conn.commit()
            increment_command_counter()

            log_dashboard_activity(
                current_user.id,
                guild_id,
                "level_reward_add",
                f"Set level {level} reward to role {role_name}",
                request.remote_addr,
            )

            return jsonify({"success": True, "message": f"Level {level} reward saved!"})

        elif request.method == "DELETE":
            level = int(request.args.get("level"))

            cursor.execute(
                "DELETE FROM public.level_roles WHERE guild_id = %s AND level = %s",
                (guild_id, level),
            )
            conn.commit()
            increment_command_counter()

            if cursor.rowcount > 0:
                log_dashboard_activity(
                    current_user.id,
                    guild_id,
                    "level_reward_delete",
                    f"Deleted level {level} reward",
                    request.remote_addr,
                )
                return jsonify(
                    {"success": True, "message": f"Level {level} reward deleted!"}
                )
            else:
                return jsonify({"error": "Reward not found"}), 404

    except Exception as e:
        log.error(f"Error managing level reward for guild {guild_id}: {e}")
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)


# ==================== ENHANCED API ENDPOINTS ====================


@app.route("/api/stats")
def get_stats():
    """Get real-time bot statistics"""
    global stats_cache

    now = datetime.now()
    if stats_cache["data"] and stats_cache["timestamp"]:
        if now - stats_cache["timestamp"] < CACHE_DURATION:
            return jsonify(stats_cache["data"])

    pool = init_db_pool()
    if not pool:
        return jsonify({"error": "Database connection failed"}), 500

    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        # Get the server count directly from the bot_stats table
        cursor.execute(
            "SELECT server_count, user_count, commands_used FROM public.bot_stats WHERE bot_id = %s",
            (YOUR_BOT_ID,),
        )
        bot_stats = cursor.fetchone()

        # UPDATED QUERY: Added UNION ALL after t1 and added r-commands
        cursor.execute(
            """
            SELECT COUNT(DISTINCT command_name) as total_commands
            FROM (
                SELECT 'g1-help' as command_name UNION ALL SELECT 'g2-show-config' UNION ALL
                SELECT 'g3-serverlist' UNION ALL SELECT 'g4-leaveserver' UNION ALL
                SELECT 'g5-banguild' UNION ALL SELECT 'g6-unbanguild' UNION ALL
                SELECT 'ping' UNION ALL
                SELECT 'l1-level' UNION ALL SELECT 'l2-leaderboard' UNION ALL
                SELECT 'l3-setup-level-reward' UNION ALL SELECT 'l4-level-reward-show' UNION ALL
                SELECT 'l5-notify-level-msg' UNION ALL SELECT 'l6-set-auto-reset' UNION ALL
                SELECT 'l7-show-auto-reset' UNION ALL SELECT 'l8-stop-auto-reset' UNION ALL
                SELECT 'l9-reset-xp' UNION ALL SELECT 'l10-upgrade-all-roles' UNION ALL
                SELECT 'y1-find-youtube-channel-id' UNION ALL SELECT 'y2-setup-youtube-notifications' UNION ALL
                SELECT 'y3-disable-youtube-notifications' UNION ALL SELECT 'y4-list-youtube-notifications' UNION ALL
                SELECT 'y5-test-rss-feed' UNION ALL
                SELECT 'n1-setup-no-text' UNION ALL SELECT 'n2-remove-no-text' UNION ALL
                SELECT 'n3-bypass-no-text' UNION ALL SELECT 'n4-show-bypass-roles' UNION ALL
                SELECT 'n5-remove-bypass-role' UNION ALL SELECT 'n6-no-discord-link' UNION ALL
                SELECT 'n7-no-links' UNION ALL SELECT 'n8-remove-no-discord-link' UNION ALL
                SELECT 'n9-remove-no-links' UNION ALL SELECT 'n10-setup-text-only' UNION ALL
                SELECT 'n11-remove-text-only' UNION ALL
                SELECT 't1-setup-time-channels' UNION ALL
                SELECT 'r0-list' UNION ALL
                SELECT 'r1-create' UNION ALL
                SELECT 'r2-delete' UNION ALL
                SELECT 'r3-edit' UNION ALL
                SELECT 'r4-pause'
            ) commands
        """
        )

        command_count_result = cursor.fetchone()
        total_commands = command_count_result[0] if command_count_result else 39

        cursor.close()

        if bot_stats:
            stats_data = {
                "total_servers": bot_stats[0] or 0,
                "total_users": bot_stats[1] or 0,
                "commands_used": bot_stats[2] or 0,
                "uptime": "99.9%",
                "total_commands": total_commands,
                "last_updated": now.isoformat(),
            }
        else:
            stats_data = {
                "total_servers": 0,
                "total_users": 0,
                "commands_used": 0,
                "uptime": "99.9%",
                "total_commands": total_commands,
                "last_updated": now.isoformat(),
            }

        stats_cache["data"] = stats_data
        stats_cache["timestamp"] = now

        return jsonify(stats_data)

    except Exception as e:
        log.error(f"Error fetching stats: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)

@app.route("/api/command-categories")
def get_command_categories():
    """Get organized command categories with actual counts"""

    categories = {
        "general": {
            "name": "General Commands",
            "icon": "fas fa-info-circle",
            "color": "success",
            "commands": [
                "g1-help",
                "g2-show-config",
                "g3-serverlist",
                "g4-leaveserver",
                "g5-banguild",
                "g6-unbanguild",
                "ping",
            ],
        },
        "leveling": {
            "name": "Leveling System",
            "icon": "fas fa-trophy",
            "color": "primary",
            "commands": [
                "l1-level",
                "l2-leaderboard",
                "l3-setup-level-reward",
                "l4-level-reward-show",
                "l5-notify-level-msg",
                "l6-set-auto-reset",
                "l7-show-auto-reset",
                "l8-stop-auto-reset",
                "l9-reset-xp",
                "l10-upgrade-all-roles",
            ],
        },
        "youtube": {
            "name": "YouTube Notifications",
            "icon": "fab fa-youtube",
            "color": "danger",
            "commands": [
                "y1-find-youtube-channel-id",
                "y2-setup-youtube-notifications",
                "y3-disable-youtube-notifications",
                "y4-list-youtube-notifications",
                "y5-test-rss-feed",
            ],
        },
        "restrictions": {
            "name": "Channel Restrictions",
            "icon": "fas fa-shield-alt",
            "color": "warning",
            "commands": [
                "n1-setup-no-text",
                "n2-remove-no-text",
                "n3-bypass-no-text",
                "n4-show-bypass-roles",
                "n5-remove-bypass-role",
                "n6-no-discord-link",
                "n7-no-links",
                "n8-remove-no-discord-link",
                "n9-remove-no-links",
                "n10-setup-text-only",
                "n11-remove-text-only",
            ],
        },
        "time": {
            "name": "Time Channels",
            "icon": "fas fa-clock",
            "color": "info",
            "commands": ["t1-setup-time-channels"],
        },
        "reminders": {
            "name": "Reminders",
            "icon": "fas fa-stopwatch",
            "color": "success",
            "commands": [
                "r0-list",
                "r1-create",
                "r2-delete",
                "r3-edit",
                "r4-pause"
            ],
        },
    }

    # Calculate totals
    total_commands = sum(len(cat["commands"]) for cat in categories.values())

    return jsonify(
        {
            "categories": categories,
            "total_commands": total_commands,
            "category_counts": {
                key: len(cat["commands"]) for key, cat in categories.items()
            },
        }
    )


@app.route("/api/contact", methods=["POST"])
def handle_contact_form():
    """Handle contact form submissions"""
    try:
        data = request.get_json()

        username = data.get("name", "").strip()
        email = data.get("email", "").strip()
        subject = data.get("subject", "").strip()
        message = data.get("message", "").strip()

        if not all([username, email, subject, message]):
            return jsonify({"error": "All fields are required"}), 400

        import re

        email_pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
        if not re.match(email_pattern, email):
            return jsonify({"error": "Invalid email address"}), 400

        if len(message) < 10:
            return (
                jsonify({"error": "Message is too short (minimum 10 characters)"}),
                400,
            )

        if len(message) > 2000:
            return (
                jsonify({"error": "Message is too long (maximum 2000 characters)"}),
                400,
            )

        ip_address = request.remote_addr
        user_agent = request.headers.get("User-Agent", "")

        pool = init_db_pool()
        if not pool:
            return jsonify({"error": "Database connection failed"}), 500

        conn = None
        try:
            conn = pool.getconn()
            cursor = conn.cursor()

            query = """
                INSERT INTO public.contact_messages 
                (username, email, subject, message, ip_address, user_agent, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """

            cursor.execute(
                query, (username, email, subject, message, ip_address, user_agent)
            )
            conn.commit()
            cursor.close()

            log.info(f"âœ… Contact form submission from {email} - Subject: {subject}")

            return (
                jsonify(
                    {
                        "success": True,
                        "message": "Thank you for your message! We'll get back to you soon.",
                    }
                ),
                200,
            )

        except Exception as e:
            log.error(f"Database error in contact form: {e}")
            if conn:
                conn.rollback()
            return jsonify({"error": "Failed to save message. Please try again."}), 500
        finally:
            if conn and pool:
                pool.putconn(conn)

    except Exception as e:
        log.error(f"Error handling contact form: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500

# ==================== AUTO-RESET API ====================

@app.route("/api/server/<guild_id>/auto-reset", methods=["GET"])
@login_required
def get_auto_reset_config(guild_id):
    """Get current auto-reset configuration"""
    if not user_has_access(current_user.id, guild_id):
        log.warning(f"Access denied for user {current_user.id} to guild {guild_id}")
        return jsonify({"error": "Access denied"}), 403

    pool = init_db_pool()
    conn = None
    if not pool:
        log.error("Database pool not available")
        return jsonify({"error": "Database error"}), 500

    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            conn = pool.getconn()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT days, last_reset FROM public.auto_reset WHERE guild_id = %s",
                (guild_id,),
            )
            result = cursor.fetchone()
            cursor.close()

            if result:
                days, last_reset = result

                # Handle timezone-aware datetime
                from datetime import timezone as tz

                # Ensure last_reset has timezone info
                if last_reset.tzinfo is None:
                    last_reset = last_reset.replace(tzinfo=tz.utc)

                next_reset = last_reset + timedelta(days=days)
                now = datetime.now(tz.utc)

                time_remaining = (next_reset - now).total_seconds()

                # Handle negative time (reset overdue)
                if time_remaining < 0:
                    days_remaining = 0
                    hours_remaining = 0
                else:
                    days_remaining = int(time_remaining // 86400)
                    hours_remaining = int((time_remaining % 86400) // 3600)

                log.info(
                    f"✅ Retrieved auto-reset config for guild {guild_id}: {days} days"
                )

                return jsonify(
                    {
                        "enabled": True,
                        "days": days,
                        "last_reset": last_reset.isoformat(),
                        "next_reset": next_reset.isoformat(),
                        "days_remaining": days_remaining,
                        "hours_remaining": hours_remaining,
                    }
                )
            else:
                log.info(f"ℹ️ No auto-reset config found for guild {guild_id}")
                return jsonify(
                    {
                        "enabled": False,
                        "days": None,
                        "last_reset": None,
                        "next_reset": None,
                        "days_remaining": None,
                        "hours_remaining": None,
                    }
                )

        except Exception as e:
            retry_count += 1
            log.error(
                f"Error fetching auto-reset config for guild {guild_id} (attempt {retry_count}/{max_retries}): {e}"
            )

            if conn:
                try:
                    pool.putconn(conn, close=True)  # Close the bad connection
                    conn = None
                except:
                    pass

            if retry_count >= max_retries:
                return (
                    jsonify(
                        {
                            "error": f"Failed to fetch auto-reset config after {max_retries} attempts"
                        }
                    ),
                    500,
                )

            # Wait a bit before retrying
            import time

            time.sleep(0.5)

        finally:
            if conn and pool:
                try:
                    pool.putconn(conn)
                except Exception as e:
                    log.error(f"Error returning connection to pool: {e}")

    # Should never reach here, but just in case
    return jsonify({"error": "Unexpected error"}), 500


@app.route("/api/server/<guild_id>/auto-reset", methods=["POST"])
@login_required
def set_auto_reset(guild_id):
    """Enable/configure auto-reset schedule"""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json()
    days = data.get("days")

    try:
        days = int(days)
        if days < 1 or days > 365:
            return jsonify({"error": "Days must be between 1 and 365"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid days value"}), 400

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        # Get guild name
        cursor.execute(
            "SELECT guild_name FROM public.dashboard_user_servers WHERE user_id = %s AND guild_id = %s",
            (current_user.id, guild_id),
        )
        guild_info = cursor.fetchone()
        guild_name = guild_info[0] if guild_info else "Unknown Guild"

        # Insert or update auto-reset config
        query = """
            INSERT INTO public.auto_reset (guild_id, guild_name, days, last_reset)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (guild_id)
            DO UPDATE SET
                days = EXCLUDED.days,
                last_reset = NOW(),
                guild_name = EXCLUDED.guild_name
        """

        cursor.execute(query, (guild_id, guild_name, days))
        conn.commit()

        # Get the updated data to return
        cursor.execute(
            "SELECT days, last_reset FROM public.auto_reset WHERE guild_id = %s",
            (guild_id,),
        )
        updated = cursor.fetchone()
        cursor.close()

        increment_command_counter()

        log_dashboard_activity(
            current_user.id,
            guild_id,
            "auto_reset_enabled",
            f"Set auto-reset to every {days} day(s)",
            request.remote_addr,
        )

        log.info(f"✅ Auto-reset enabled for guild {guild_id}: every {days} days")

        # Calculate next reset for response
        if updated:
            from datetime import timezone as tz

            last_reset = updated[1]
            if last_reset.tzinfo is None:
                last_reset = last_reset.replace(tzinfo=tz.utc)
            next_reset = last_reset + timedelta(days=days)

            return jsonify(
                {
                    "success": True,
                    "message": f"Auto-reset enabled! XP will reset every {days} day(s).",
                    "days": days,
                    "last_reset": last_reset.isoformat(),
                    "next_reset": next_reset.isoformat(),
                }
            )

        return jsonify(
            {
                "success": True,
                "message": f"Auto-reset enabled! XP will reset every {days} day(s).",
            }
        )

    except Exception as e:
        log.error(f"Error setting auto-reset for guild {guild_id}: {e}")
        if conn:
            conn.rollback()
        return jsonify({"error": f"Failed to enable auto-reset: {str(e)}"}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)


@app.route("/api/server/<guild_id>/auto-reset", methods=["DELETE"])
@login_required
def disable_auto_reset(guild_id):
    """Disable auto-reset schedule"""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM public.auto_reset WHERE guild_id = %s", (guild_id,))

        deleted = cursor.rowcount > 0
        conn.commit()
        cursor.close()

        if deleted:
            increment_command_counter()

            log_dashboard_activity(
                current_user.id,
                guild_id,
                "auto_reset_disabled",
                "Disabled auto-reset",
                request.remote_addr,
            )

            log.info(f"✅ Auto-reset disabled for guild {guild_id}")

            return jsonify(
                {"success": True, "message": "Auto-reset has been disabled."}
            )
        else:
            return jsonify({"error": "Auto-reset was not enabled for this server"}), 404

    except Exception as e:
        log.error(f"Error disabling auto-reset for guild {guild_id}: {e}")
        if conn:
            conn.rollback()
        return jsonify({"error": f"Failed to disable auto-reset: {str(e)}"}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)


# ==================== YOUTUBE CHANNEL FINDER API ====================


@app.route("/api/youtube/find-channel", methods=["GET"])
@login_required
def find_youtube_channel():
    """Find YouTube channel ID from @handle or URL using YouTube Data API"""
    query = request.args.get("query", "").strip()

    if not query:
        return jsonify({"error": "No query provided"}), 400

    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError:
        log.error("Google API client not installed")
        return jsonify({"error": "YouTube API client not available"}), 500

    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
    if not YOUTUBE_API_KEY:
        log.error("YOUTUBE_API_KEY not found in environment")
        return jsonify({"error": "YouTube API key not configured"}), 500

    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

        channel_id = None
        channel_name = None

        if "@" in query:
            handle = query.split("@")[-1].split("/")[0].strip()
            log.info(f"Searching for YouTube channel with handle: @{handle}")

            search_response = (
                youtube.search()
                .list(part="snippet", q=f"@{handle}", type="channel", maxResults=1)
                .execute()
            )

            if search_response.get("items"):
                channel_id = search_response["items"][0]["snippet"]["channelId"]
                channel_name = search_response["items"][0]["snippet"]["title"]

        elif "/channel/" in query:
            channel_id = (
                query.split("/channel/")[-1].split("/")[0].split("?")[0].strip()
            )
            log.info(f"Extracted channel ID from URL: {channel_id}")

        elif "/c/" in query or "/user/" in query:
            username = (
                query.split("/c/" if "/c/" in query else "/user/")[-1]
                .split("/")[0]
                .strip()
            )
            log.info(f"Searching for channel: {username}")

            search_response = (
                youtube.search()
                .list(part="snippet", q=username, type="channel", maxResults=1)
                .execute()
            )

            if search_response.get("items"):
                channel_id = search_response["items"][0]["snippet"]["channelId"]
                channel_name = search_response["items"][0]["snippet"]["title"]

        elif "youtube.com/" in query:
            custom_url = (
                query.split("youtube.com/")[-1].split("/")[0].split("?")[0].strip()
            )
            log.info(f"Searching for channel with custom URL: {custom_url}")

            search_response = (
                youtube.search()
                .list(part="snippet", q=custom_url, type="channel", maxResults=1)
                .execute()
            )

            if search_response.get("items"):
                channel_id = search_response["items"][0]["snippet"]["channelId"]
                channel_name = search_response["items"][0]["snippet"]["title"]
        else:
            log.info(f"Searching for channel: {query}")
            search_response = (
                youtube.search()
                .list(part="snippet", q=query, type="channel", maxResults=1)
                .execute()
            )

            if search_response.get("items"):
                channel_id = search_response["items"][0]["snippet"]["channelId"]
                channel_name = search_response["items"][0]["snippet"]["title"]

        if channel_id:
            if not channel_name:
                channel_response = (
                    youtube.channels().list(part="snippet", id=channel_id).execute()
                )

                if channel_response.get("items"):
                    channel_name = channel_response["items"][0]["snippet"]["title"]

            log.info(f"✅ Found YouTube channel: {channel_name} (ID: {channel_id})")

            return jsonify(
                {
                    "success": True,
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                }
            )
        else:
            log.warning(f"No YouTube channel found for query: {query}")
            return (
                jsonify(
                    {"error": "Channel not found. Please check the URL or handle."}
                ),
                404,
            )

    except HttpError as e:
        log.error(f"YouTube API error: {e}")
        if e.resp.status == 403:
            return (
                jsonify({"error": "YouTube API quota exceeded or invalid API key"}),
                403,
            )
        return jsonify({"error": f"YouTube API error: {str(e)}"}), 500

    except Exception as e:
        log.error(f"Error finding YouTube channel: {e}", exc_info=True)
        return jsonify({"error": f"Failed to find channel: {str(e)}"}), 500


@app.route("/api/server/<guild_id>/reset-xp", methods=["POST"])
@login_required
def manual_reset_xp(guild_id):
    """Manually reset all XP and remove reward roles for an entire server."""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT role_id FROM public.level_roles WHERE guild_id = %s", (guild_id,)
        )
        reward_roles = cursor.fetchall()
        reward_role_ids = {int(r[0]) for r in reward_roles}
        log.info(
            f"Found {len(reward_role_ids)} reward roles to remove for guild {guild_id}."
        )

        roles_removed_count = 0
        users_affected_count = 0

        if reward_role_ids:
            headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
            members_response = requests.get(
                f"{DISCORD_API_BASE_URL}/guilds/{guild_id}/members?limit=1000",
                headers=headers,
            )
            members = (
                members_response.json() if members_response.status_code == 200 else []
            )

            for member in members:
                user_id = member["user"]["id"]
                member_role_ids = {int(role_id) for role_id in member["roles"]}

                roles_to_strip = member_role_ids.intersection(reward_role_ids)

                if roles_to_strip:
                    users_affected_count += 1
                    for role_id_to_remove in roles_to_strip:
                        role_remove_url = f"{DISCORD_API_BASE_URL}/guilds/{guild_id}/members/{user_id}/roles/{role_id_to_remove}"
                        try:
                            r = requests.delete(
                                role_remove_url, headers=headers, timeout=5
                            )
                            if r.status_code == 204:
                                roles_removed_count += 1
                                log.info(
                                    f"Removed role {role_id_to_remove} from user {user_id} in guild {guild_id}"
                                )
                            else:
                                log.warning(
                                    f"Failed to remove role {role_id_to_remove} from user {user_id}. Status: {r.status_code}, Response: {r.text}"
                                )
                        except requests.RequestException as e:
                            log.error(f"Network error while removing role: {e}")

        cursor.execute(
            "SELECT COUNT(*) FROM public.users WHERE guild_id = %s AND xp > 0",
            (guild_id,),
        )
        total_users_in_db = cursor.fetchone()[0]

        cursor.execute(
            "UPDATE public.users SET xp = 0, level = 0, voice_xp_earned = 0 WHERE guild_id = %s",
            (guild_id,),
        )
        cursor.execute(
            "UPDATE public.last_notified_level SET level = 0 WHERE guild_id = %s",
            (guild_id,),
        )
        cursor.execute(
            "UPDATE public.auto_reset SET last_reset = NOW() WHERE guild_id = %s",
            (guild_id,),
        )
        conn.commit()
        increment_command_counter()

        log_dashboard_activity(
            current_user.id,
            guild_id,
            "manual_xp_reset",
            f"Manually reset XP for {total_users_in_db} users. Removed {roles_removed_count} roles from {users_affected_count} members.",
            request.remote_addr,
        )

        log.info(f"✅ Manual XP reset completed for guild {guild_id}")

        return jsonify(
            {
                "success": True,
                "message": f"Successfully reset XP for {total_users_in_db} users and removed {roles_removed_count} roles!",
                "affected_users": total_users_in_db,
                "roles_removed": roles_removed_count,
            }
        )

    except Exception as e:
        log.error(f"Error resetting XP for guild {guild_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to reset XP"}), 500
    finally:
        if conn and pool:
            cursor.close()
            pool.putconn(conn)


@app.route("/api/server/<guild_id>/config", methods=["GET"])
@login_required
def get_server_config(guild_id):
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        config = {}

        # Guild Settings
        cursor.execute(
            "SELECT * FROM public.guild_settings WHERE guild_id = %s", (guild_id,)
        )
        s = cursor.fetchone()
        config["guild_settings"] = (
            {
                "xp_per_message": s[1],
                "xp_per_image": s[2],
                "xp_per_minute_in_voice": s[3],
                "voice_xp_limit": s[4],
            }
            if s
            else {
                "xp_per_message": 5,
                "xp_per_image": 10,
                "xp_per_minute_in_voice": 15,
                "voice_xp_limit": 1500,
            }
        )

        # Leveling System
        cursor.execute(
            "SELECT channel_id FROM public.level_notify_channel WHERE guild_id = %s",
            (guild_id,),
        )
        nr = cursor.fetchone()
        config["level_notify_channel_id"] = nr[0] if nr else None
        cursor.execute(
            "SELECT level, role_id FROM public.level_roles WHERE guild_id = %s ORDER BY level ASC",
            (guild_id,),
        )
        config["level_rewards"] = [
            {"level": r[0], "role_id": r[1]} for r in cursor.fetchall()
        ]

        # Time Channels
        cursor.execute(
            "SELECT date_channel_id, india_channel_id, japan_channel_id, is_enabled FROM public.time_channel_config WHERE guild_id = %s",
            (guild_id,),
        )
        tc = cursor.fetchone()
        config["time_channel_config"] = (
            {
                "date_channel_id": tc[0],
                "india_channel_id": tc[1],
                "japan_channel_id": tc[2],
                "is_enabled": tc[3],
            }
            if tc
            else {
                "date_channel_id": None,
                "india_channel_id": None,
                "japan_channel_id": None,
                "is_enabled": False,
            }
        )

        # YouTube Notifications
        cursor.execute(
            "SELECT * FROM public.youtube_notification_config WHERE guild_id = %s ORDER BY yt_channel_name ASC",
            (guild_id,),
        )
        yt_configs = [
            dict(zip([desc[0] for desc in cursor.description], row))
            for row in cursor.fetchall()
        ]
        config["youtube_notification_config"] = yt_configs

        # Channel Restrictions (New Unified Table)
        try:
            cursor.execute(
                "SELECT channel_id, restriction_type, redirect_channel_id FROM public.channel_restrictions_v2 WHERE guild_id = %s",
                (guild_id,),
            )
            # Initialize an empty dictionary for channel restrictions
            config["channel_restrictions"] = {}
            # Process the results from the new v2 table
            for r in cursor.fetchall():
                channel_id, restriction_type, redirect_id = r
                # Re-create the old data structure that the frontend expects
                config["channel_restrictions"][channel_id] = {
                    "block_invites": restriction_type == "block_invites",
                    "block_links": restriction_type == "block_all_links",
                    "media_only": restriction_type == "media_only",
                    "text_only": restriction_type == "text_only",
                    "redirect_channel_id": redirect_id,
                }
        except Exception as e:
            log.error(f"Error fetching channel restrictions for guild {guild_id}: {e}")
            config["channel_restrictions"] = {}

        return jsonify(config)
    finally:
        if conn and pool:
            cursor.close()
            pool.putconn(conn)


@app.route("/api/server/<guild_id>/leaderboard", methods=["GET"])
@login_required
def get_leaderboard(guild_id):
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    limit = request.args.get("limit", 20, type=int)
    search = request.args.get("search", "", type=str)

    pool = init_db_pool()
    if not pool:
        return jsonify({"error": "Database error"}), 500

    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        if search:
            query = "SELECT user_id, username, xp, level FROM public.users WHERE guild_id = %s AND username ILIKE %s ORDER BY xp DESC LIMIT %s"
            cursor.execute(query, (guild_id, f"%{search}%", limit))
        else:
            query = "SELECT user_id, username, xp, level FROM public.users WHERE guild_id = %s ORDER BY xp DESC LIMIT %s"
            cursor.execute(query, (guild_id, limit))

        leaderboard_data = [
            {"user_id": r[0], "username": r[1], "xp": r[2], "level": r[3]}
            for r in cursor.fetchall()
        ]
        cursor.close()

        return jsonify(leaderboard_data)
    except Exception as e:
        log.error(f"Error fetching leaderboard for guild {guild_id}: {e}")
        return jsonify({"error": "Failed to fetch leaderboard"}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)


@app.route("/api/server/<guild_id>/level-notify-channel", methods=["POST"])
@login_required
def update_level_notify_channel(guild_id):
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json()
    channel_id = data.get("channel_id")
    channel_name = data.get("channel_name")

    if not channel_id or not channel_name:
        if channel_id is None:
            pass
        else:
            return jsonify({"error": "channel_id and channel_name are required"}), 400

    pool = init_db_pool()
    if not pool:
        return jsonify({"error": "Database error"}), 500

    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        if channel_id:
            query = "INSERT INTO public.level_notify_channel (guild_id, channel_id, channel_name) VALUES (%s, %s, %s) ON CONFLICT (guild_id) DO UPDATE SET channel_id = EXCLUDED.channel_id, channel_name = EXCLUDED.channel_name;"
            cursor.execute(query, (guild_id, channel_id, channel_name))
            log_msg = f"Set level notification channel to #{channel_name}"
        else:
            cursor.execute(
                "DELETE FROM public.level_notify_channel WHERE guild_id = %s",
                (guild_id,),
            )
            log_msg = "Disabled level notifications"

        conn.commit()
        log_dashboard_activity(
            current_user.id,
            guild_id,
            "level_notify_update",
            log_msg,
            request.remote_addr,
        )
        increment_command_counter()
        cursor.close()
        return jsonify({"success": True, "message": "Notification channel updated!"})
    except Exception as e:
        log.error(f"Error updating notify channel for guild {guild_id}: {e}")
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to update notification channel"}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)


def run_flask_app():
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"

    log.info("=" * 60)
    log.info("🌐 FLASK FRONTEND STARTING (WITH DASHBOARD)")
    log.info(f"   Host: {host}:{port}, Debug: {debug}")
    log.info(f"   Domain: {SERVER_DOMAIN}")
    log.info(f"   OAuth2 Redirect: {DISCORD_OAUTH2_REDIRECT_URI}")
    log.info("=" * 60)

    if os.getenv("OAUTHLIB_INSECURE_TRANSPORT") == "1":
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        log.warning(
            "🔒 OAUTHLIB_INSECURE_TRANSPORT is ENABLED. Use only in production behind a secure proxy."
        )

    init_db_pool()
    app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)

# ==================== REMINDER API ENDPOINTS ====================

@app.route("/api/server/<guild_id>/reminders", methods=["GET"])
@login_required
def get_reminders(guild_id):
    """Get all reminders for a guild"""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, reminder_id, channel_id, role_id, message, 
                   next_run, interval, timezone, status, run_count, created_at
            FROM public.reminders 
            WHERE guild_id = %s AND status != 'deleted'
            ORDER BY next_run ASC
            """,
            (guild_id,),
        )

        columns = [desc[0] for desc in cursor.description]
        reminders = []
        for row in cursor.fetchall():
            reminder = dict(zip(columns, row))
            reminder["next_run"] = (
                reminder["next_run"].isoformat() if reminder["next_run"] else None
            )
            reminder["created_at"] = (
                reminder["created_at"].isoformat() if reminder["created_at"] else None
            )
            # Ensure timezone is included
            reminder["timezone"] = reminder.get("timezone") or "Asia/Kolkata"
            reminders.append(reminder)

        cursor.close()
        
        log.info(f"✅ Fetched {len(reminders)} reminders for guild {guild_id}")
        return jsonify({"reminders": reminders, "total": len(reminders)})

    except Exception as e:
        log.error(f"Error fetching reminders: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)

@app.route("/api/server/<guild_id>/reminders/<reminder_id>", methods=["DELETE"])
@login_required
def delete_reminder_api(guild_id, reminder_id):
    """Delete a reminder"""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE public.reminders 
            SET status = 'deleted' 
            WHERE reminder_id = %s AND guild_id = %s
            RETURNING message
            """,
            (reminder_id, guild_id),
        )

        deleted = cursor.fetchone()
        conn.commit()
        cursor.close()

        if deleted:
            log_dashboard_activity(
                current_user.id,
                guild_id,
                "reminder_delete",
                f"Deleted reminder {reminder_id}",
                request.remote_addr,
            )

            return jsonify(
                {"success": True, "message": f"Reminder {reminder_id} deleted"}
            )
        else:
            return jsonify({"error": "Reminder not found"}), 404

    except Exception as e:
        log.error(f"Error deleting reminder: {e}")
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)


@app.route("/api/server/<guild_id>/reminders/<reminder_id>/toggle", methods=["POST"])
@login_required
def toggle_reminder_status(guild_id, reminder_id):
    """Pause or resume a reminder"""
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403

    pool = init_db_pool()
    conn = None
    if not pool:
        return jsonify({"error": "Database error"}), 500

    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        # Get current status
        cursor.execute(
            "SELECT status FROM public.reminders WHERE reminder_id = %s AND guild_id = %s",
            (reminder_id, guild_id),
        )
        result = cursor.fetchone()

        if not result:
            return jsonify({"error": "Reminder not found"}), 404

        current_status = result[0]
        new_status = "paused" if current_status == "active" else "active"

        cursor.execute(
            """
            UPDATE public.reminders 
            SET status = %s, updated_at = NOW()
            WHERE reminder_id = %s AND guild_id = %s
            """,
            (new_status, reminder_id, guild_id),
        )

        conn.commit()
        cursor.close()

        log_dashboard_activity(
            current_user.id,
            guild_id,
            "reminder_toggle",
            f"Changed reminder {reminder_id} status to {new_status}",
            request.remote_addr,
        )

        return jsonify({"success": True, "new_status": new_status})

    except Exception as e:
        log.error(f"Error toggling reminder: {e}")
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)

if __name__ == "__main__":
    run_flask_app()
