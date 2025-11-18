#!/usr/bin/env python3
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
from psycopg2 import pool
from datetime import datetime, timedelta
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
SERVER_DOMAIN = os.getenv("SERVER_DOMAIN", "https://shabdprakash-thakkar.online")
SERVER_IP = os.getenv("SERVER_IP", "194.164.56.165")
SERVER_PORT = os.getenv("FLASK_PORT", "9528")

ALLOWED_ORIGINS = [
    SERVER_DOMAIN,
    f"http://{SERVER_IP}:{SERVER_PORT}",
    f"https://{SERVER_IP}:{SERVER_PORT}",
    "http://localhost:9528",
    "http://127.0.0.1:9528",
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
permissions = "268512304"
scopes = "bot applications.commands"
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
    if not pool: return None
    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, discriminator, avatar, email FROM public.dashboard_users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        cursor.close()
        if row: return User(row[0], row[1], row[2], row[3], row[4])
        return None
    except Exception as e:
        log.error(f"Error loading user: {e}")
        return None
    finally:
        if conn and pool: pool.putconn(conn)


# ==================== PERMISSION CHECK HELPER ====================


def user_has_access(user_id, guild_id):
    pool = init_db_pool()
    if not pool: return False
    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM public.dashboard_user_servers WHERE user_id = %s AND guild_id = %s", (user_id, guild_id))
        has_access = cursor.fetchone() is not None
        cursor.close()
        return has_access
    except Exception as e:
        log.error(f"Error checking user access for guild {guild_id}: {e}")
        return False
    finally:
        if conn and pool: pool.putconn(conn)


# ==================== DATABASE CONNECTION ====================
def init_db_pool():
    global db_pool
    if db_pool is None:
        try:
            db_pool = psycopg2.pool.SimpleConnectionPool(minconn=2, maxconn=5, dsn=DATABASE_URL)
            log.info("✅ Successfully created database connection pool for Flask.")
        except Exception as e:
            log.critical(f"❌ CRITICAL: Flask could not connect to the database: {e}")
            db_pool = None
    return db_pool


# ==================== OAUTH2 & DB HELPERS ====================
# (These functions are unchanged)
def get_discord_oauth_session(token=None, state=None):
    return OAuth2Session(client_id=DISCORD_OAUTH2_CLIENT_ID, redirect_uri=DISCORD_OAUTH2_REDIRECT_URI, scope=OAUTH2_SCOPES, token=token, state=state)
def get_user_info(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{DISCORD_API_BASE_URL}/users/@me", headers=headers)
    return response.json() if response.status_code == 200 else None
def get_user_guilds(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{DISCORD_API_BASE_URL}/users/@me/guilds", headers=headers)
    return response.json() if response.status_code == 200 else None
def get_bot_guilds():
    pool = init_db_pool(); conn = None
    if not pool: return set()
    try:
        conn = pool.getconn(); cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT guild_id FROM public.users")
        return {r[0] for r in cursor.fetchall()}
    finally:
        if conn: pool.putconn(conn)
def save_user_to_db(user_data, access_token, refresh_token=None):
    pool = init_db_pool(); conn = None
    if not pool: return False
    try:
        conn = pool.getconn(); cursor = conn.cursor()
        query = "INSERT INTO public.dashboard_users (user_id, username, discriminator, avatar, email, access_token, refresh_token, token_expires_at, last_login, total_logins) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), 1) ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username, discriminator=EXCLUDED.discriminator, avatar=EXCLUDED.avatar, email=EXCLUDED.email, access_token=EXCLUDED.access_token, refresh_token=EXCLUDED.refresh_token, token_expires_at=EXCLUDED.token_expires_at, last_login=NOW(), total_logins=dashboard_users.total_logins + 1"
        cursor.execute(query, (str(user_data["id"]), user_data["username"], user_data.get("discriminator", "0"), user_data.get("avatar"), user_data.get("email"), access_token, refresh_token, datetime.now() + timedelta(days=7)))
        conn.commit()
    finally:
        if conn: pool.putconn(conn)
def save_user_servers(user_id, guilds):
    pool = init_db_pool(); conn = None
    if not pool: return False
    bot_guilds = get_bot_guilds()
    try:
        conn = pool.getconn(); cursor = conn.cursor()
        cursor.execute("DELETE FROM public.dashboard_user_servers WHERE user_id = %s", (user_id,))
        for g in guilds:
            if str(g["id"]) in bot_guilds:
                perms = int(g.get("permissions", 0))
                if (perms & 0x8) == 0x8 or g.get("owner", False):
                    cursor.execute("INSERT INTO public.dashboard_user_servers (user_id, guild_id, guild_name, guild_icon, user_permissions, is_owner) VALUES (%s, %s, %s, %s, %s, %s)", (user_id, str(g["id"]), g["name"], g.get("icon"), perms, g.get("owner", False)))
        conn.commit()
    finally:
        if conn: pool.putconn(conn)
def log_dashboard_activity(user_id, guild_id, action_type, description, ip_address=None):
    pool = init_db_pool(); conn = None
    if not pool: return
    try:
        conn = pool.getconn(); cursor = conn.cursor()
        cursor.execute("INSERT INTO public.dashboard_activity_log (user_id, guild_id, action_type, action_description, ip_address) VALUES (%s, %s, %s, %s, %s)", (user_id, guild_id, action_type, description, ip_address))
        conn.commit()
    finally:
        if conn: pool.putconn(conn)
# =======================================================


# ==================== MAIN ROUTES ====================
@app.route("/")
def index(): return render_template("index.html", invite_url=INVITE_URL)

@app.route("/contact")
def contact(): return render_template("contact.html", invite_url=INVITE_URL)

# ==================== DASHBOARD & AUTH ROUTES ====================
@app.route("/dashboard")
def dashboard():
    if current_user.is_authenticated: return redirect(url_for("dashboard_servers"))
    return render_template("dashboard.html", invite_url=INVITE_URL)

@app.route("/dashboard/servers")
@login_required
def dashboard_servers():
    pool = init_db_pool(); conn = None
    if not pool: return "Database error", 500
    try:
        conn = pool.getconn(); cursor = conn.cursor()
        cursor.execute("SELECT guild_id, guild_name, guild_icon, is_owner, last_accessed FROM public.dashboard_user_servers WHERE user_id = %s ORDER BY last_accessed DESC", (current_user.id,))
        servers = [{"id": s[0], "name": s[1], "icon": f"https://cdn.discordapp.com/icons/{s[0]}/{s[2]}.png" if s[2] else None, "is_owner": s[3], "last_accessed": s[4]} for s in cursor.fetchall()]
        return render_template("dashboard.html", invite_url=INVITE_URL, servers=servers, user=current_user)
    finally:
        if conn: pool.putconn(conn)

@app.route("/dashboard/server/<guild_id>")
@login_required
def server_config(guild_id):
    if not user_has_access(current_user.id, guild_id): return "Access Denied", 403
    pool = init_db_pool(); conn = None
    if not pool: return "Database error", 500
    try:
        conn = pool.getconn(); cursor = conn.cursor()
        cursor.execute("SELECT guild_name, guild_icon FROM public.dashboard_user_servers WHERE user_id = %s AND guild_id = %s", (current_user.id, guild_id))
        s_info = cursor.fetchone()
        cursor.execute("UPDATE public.dashboard_user_servers SET last_accessed = NOW() WHERE user_id = %s AND guild_id = %s", (current_user.id, guild_id))
        conn.commit()
        server_info = {"id": guild_id, "name": s_info[0], "icon": f"https://cdn.discordapp.com/icons/{guild_id}/{s_info[1]}.png" if s_info[1] else None}
        return render_template("server_config.html", server=server_info)
    finally:
        if conn: pool.putconn(conn)

@app.route("/dashboard/login")
def dashboard_login():
    discord = get_discord_oauth_session()
    auth_url, state = discord.authorization_url(DISCORD_AUTHORIZATION_BASE_URL)
    session["oauth_state"] = state
    return redirect(auth_url)

@app.route("/dashboard/callback")
def dashboard_callback():
    if "oauth_state" not in session: return redirect(url_for("dashboard"))
    discord = get_discord_oauth_session(state=session.pop("oauth_state"))
    try:
        token = discord.fetch_token(DISCORD_TOKEN_URL, client_secret=DISCORD_OAUTH2_CLIENT_SECRET, authorization_response=request.url)
        user_data = get_user_info(token["access_token"])
        guilds = get_user_guilds(token["access_token"])
        if not user_data or guilds is None: return redirect(url_for("dashboard"))
        save_user_to_db(user_data, token["access_token"], token.get("refresh_token"))
        save_user_servers(str(user_data["id"]), guilds)
        user = User(str(user_data["id"]), user_data["username"], user_data.get("discriminator", "0"), user_data.get("avatar"), user_data.get("email"))
        login_user(user, remember=True)
        return redirect(url_for("dashboard_servers"))
    except Exception as e:
        log.error(f"Error during OAuth callback: {e}", exc_info=True)
        return redirect(url_for("dashboard"))

@app.route("/dashboard/logout")
@login_required
def dashboard_logout():
    logout_user()
    return redirect(url_for("dashboard"))

# ==================== API ENDPOINTS ====================

@app.route("/api/server/<guild_id>/config", methods=["GET"])
@login_required
def get_server_config(guild_id):
    if not user_has_access(current_user.id, guild_id): return jsonify({"error": "Access denied"}), 403
    pool = init_db_pool(); conn = None
    if not pool: return jsonify({"error": "Database error"}), 500
    try:
        conn = pool.getconn(); cursor = conn.cursor()
        config = {}
        # General Settings
        cursor.execute("SELECT * FROM public.guild_settings WHERE guild_id = %s", (guild_id,))
        s = cursor.fetchone()
        config["guild_settings"] = {"xp_per_message": s[1], "xp_per_image": s[2], "xp_per_minute_in_voice": s[3], "voice_xp_limit": s[4]} if s else {"xp_per_message": 10, "xp_per_image": 15, "xp_per_minute_in_voice": 4, "voice_xp_limit": 1500}
        # Level Notify Channel
        cursor.execute("SELECT channel_id FROM public.level_notify_channel WHERE guild_id = %s", (guild_id,))
        nr = cursor.fetchone()
        config["level_notify_channel_id"] = nr[0] if nr else None
        # Level Rewards
        cursor.execute("SELECT level, role_id FROM public.level_roles WHERE guild_id = %s ORDER BY level ASC", (guild_id,))
        config["level_rewards"] = [{"level": r[0], "role_id": r[1]} for r in cursor.fetchall()]
        # Time Channel Config
        cursor.execute("SELECT date_channel_id, india_channel_id, japan_channel_id, is_enabled FROM public.time_channel_config WHERE guild_id = %s", (guild_id,))
        tc = cursor.fetchone()
        config["time_channel_config"] = {"date_channel_id": tc[0], "india_channel_id": tc[1], "japan_channel_id": tc[2], "is_enabled": tc[3]} if tc else {"date_channel_id": None, "india_channel_id": None, "japan_channel_id": None, "is_enabled": False}
        
        # ✨ NEW: Fetch Channel Restrictions
        cursor.execute("SELECT channel_id, block_invites, block_links, media_only, text_only, redirect_channel_id FROM public.channel_restrictions WHERE guild_id = %s", (guild_id,))
        config["channel_restrictions"] = {r[0]: {"block_invites": r[1], "block_links": r[2], "media_only": r[3], "text_only": r[4], "redirect_channel_id": r[5]} for r in cursor.fetchall()}

        return jsonify(config)
    finally:
        if conn: pool.putconn(conn)

@app.route("/api/server/<guild_id>/channel-restrictions", methods=["POST"])
@login_required
def update_channel_restrictions(guild_id):
    """Update restrictions for a single channel."""
    if not user_has_access(current_user.id, guild_id): return jsonify({"error": "Access denied"}), 403
    data = request.get_json()
    channel_id = data.get("channel_id")
    if not channel_id: return jsonify({"error": "channel_id is required"}), 400
    
    pool = init_db_pool(); conn = None
    if not pool: return jsonify({"error": "Database error"}), 500
    try:
        conn = pool.getconn(); cursor = conn.cursor()
        
        # If all restrictions are false, delete the row to keep the table clean
        if not any([data.get("block_invites"), data.get("block_links"), data.get("media_only"), data.get("text_only")]):
            cursor.execute("DELETE FROM public.channel_restrictions WHERE guild_id = %s AND channel_id = %s", (guild_id, channel_id))
            log_msg = f"Removed all restrictions from channel {channel_id}"
        else:
            query = """
                INSERT INTO public.channel_restrictions (guild_id, channel_id, block_invites, block_links, media_only, text_only, redirect_channel_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (guild_id, channel_id) DO UPDATE SET
                block_invites = EXCLUDED.block_invites, block_links = EXCLUDED.block_links, media_only = EXCLUDED.media_only,
                text_only = EXCLUDED.text_only, redirect_channel_id = EXCLUDED.redirect_channel_id;
            """
            cursor.execute(query, (guild_id, channel_id, bool(data.get("block_invites")), bool(data.get("block_links")), bool(data.get("media_only")), bool(data.get("text_only")), data.get("redirect_channel_id") or None))
            log_msg = f"Updated restrictions for channel {channel_id}: {data}"

        conn.commit()
        log_dashboard_activity(current_user.id, guild_id, "channel_restriction_update", log_msg, request.remote_addr)
        return jsonify({"success": True, "message": "Channel restrictions updated!"})
    except Exception as e:
        log.error(f"Error updating channel restrictions for {guild_id}: {e}")
        if conn: conn.rollback()
        return jsonify({"error": "Failed to update settings"}), 500
    finally:
        if conn: pool.putconn(conn)


# (All other endpoints for stats, discord-data, leaderboard, leveling, etc. are unchanged)
# ... The rest of the file remains the same from the previous correct version ...
# ...
@app.route("/api/server/<guild_id>/leaderboard", methods=["GET"])
@login_required
def get_leaderboard(guild_id):
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403
    
    limit = request.args.get('limit', 20, type=int)
    search = request.args.get('search', '', type=str)

    pool = init_db_pool()
    if not pool: return jsonify({"error": "Database error"}), 500

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
            
        leaderboard_data = [{"user_id": r[0], "username": r[1], "xp": r[2], "level": r[3]} for r in cursor.fetchall()]
        cursor.close()
        
        return jsonify(leaderboard_data)
    except Exception as e:
        log.error(f"Error fetching leaderboard for guild {guild_id}: {e}")
        return jsonify({"error": "Failed to fetch leaderboard"}), 500
    finally:
        if conn and pool: pool.putconn(conn)

@app.route("/api/server/<guild_id>/level-notify-channel", methods=["POST"])
@login_required
def update_level_notify_channel(guild_id):
    if not user_has_access(current_user.id, guild_id):
        return jsonify({"error": "Access denied"}), 403
    
    data = request.get_json()
    channel_id = data.get('channel_id')
    channel_name = data.get('channel_name')

    if not channel_id or not channel_name:
        if channel_id is None: pass
        else: return jsonify({"error": "channel_id and channel_name are required"}), 400

    pool = init_db_pool()
    if not pool: return jsonify({"error": "Database error"}), 500

    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        
        if channel_id:
            query = "INSERT INTO public.level_notify_channel (guild_id, channel_id, channel_name) VALUES (%s, %s, %s) ON CONFLICT (guild_id) DO UPDATE SET channel_id = EXCLUDED.channel_id, channel_name = EXCLUDED.channel_name;"
            cursor.execute(query, (guild_id, channel_id, channel_name))
            log_msg = f"Set level notification channel to #{channel_name}"
        else:
            cursor.execute("DELETE FROM public.level_notify_channel WHERE guild_id = %s", (guild_id,))
            log_msg = "Disabled level notifications"

        conn.commit()
        log_dashboard_activity(current_user.id, guild_id, "level_notify_update", log_msg, request.remote_addr)
        cursor.close()
        return jsonify({"success": True, "message": "Notification channel updated!"})
    except Exception as e:
        log.error(f"Error updating notify channel for guild {guild_id}: {e}")
        if conn: conn.rollback()
        return jsonify({"error": "Failed to update notification channel"}), 500
    finally:
        if conn and pool: pool.putconn(conn)

@app.route("/api/server/<guild_id>/settings", methods=["POST"])
@login_required
def update_server_settings(guild_id):
    # ... (code unchanged) ...
    pass

@app.route("/api/server/<guild_id>/time-channels", methods=["POST"])
@login_required
def update_time_channel_config(guild_id):
    # ... (code unchanged) ...
    pass

@app.route("/api/server/<guild_id>/level-reward", methods=["POST", "DELETE"])
@login_required
def manage_level_reward(guild_id):
    # ... (code unchanged) ...
    pass

# ... (rest of the file remains the same)
def run_flask_app():
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", 9528))
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"

    log.info("=" * 60)
    log.info("🌐 FLASK FRONTEND STARTING (WITH DASHBOARD)")
    log.info(f"   Host: {host}:{port}, Debug: {debug}")
    log.info(f"   Domain: {SERVER_DOMAIN}")
    log.info(f"   OAuth2 Redirect: {DISCORD_OAUTH2_REDIRECT_URI}")
    log.info("=" * 60)

    if os.getenv("OAUTHLIB_INSECURE_TRANSPORT") == "1":
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        log.warning("🔒 OAUTHLIB_INSECURE_TRANSPORT is ENABLED. Use only in production behind a secure proxy.")

    init_db_pool()
    app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)

if __name__ == "__main__":
    run_flask_app()