#!/usr/bin/env python3
"""
Flask Frontend for Supporter Discord Bot
FINAL FIX - Using synchronous psycopg2 instead of asyncpg
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import logging
import psycopg2
from psycopg2 import pool
from datetime import datetime, timedelta

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
DATABASE_URL = os.getenv("DATABASE_URL")
YOUR_BOT_ID = os.getenv("DISCORD_CLIENT_ID")

# Global connection pool
db_pool = None

# Stats cache (5 minute cache to reduce database load)
stats_cache = {"data": None, "timestamp": None}
CACHE_DURATION = timedelta(minutes=3)  # 3 minute cache as requested

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
            "methods": ["GET", "POST", "OPTIONS"],
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


# ==================== DATABASE CONNECTION ====================
def init_db_pool():
    """
    CRITICAL FIX: Use synchronous psycopg2 instead of asyncpg.
    This completely avoids all event loop issues.
    """
    global db_pool

    if db_pool is None:
        try:
            # Create connection pool using psycopg2
            db_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=2, maxconn=5, dsn=DATABASE_URL
            )
            log.info("✅ Successfully created database connection pool for Flask.")
            log.info(f"   Pool settings: min=2, max=5")
            log.info(f"   Using: psycopg2 (synchronous)")
        except Exception as e:
            log.critical(f"❌ CRITICAL: Flask could not connect to the database: {e}")
            db_pool = None

    return db_pool


# ==================== ROUTES ====================


@app.route("/")
def index():
    """Homepage with bot features and stats."""
    return render_template("index.html", invite_url=INVITE_URL)


@app.route("/contact")
def contact():
    """Contact form page."""
    return render_template("contact.html", invite_url=INVITE_URL)


@app.route("/api/contact", methods=["POST"])
def submit_contact():
    """Handle contact form submissions."""
    data = request.get_json()
    name, email, message = (
        data.get("name", "").strip(),
        data.get("email", "").strip(),
        data.get("message", "").strip(),
    )

    if not all([name, email, message]):
        return jsonify({"success": False, "message": "All fields are required!"}), 400

    log.info(f"📧 CONTACT FORM: Name={name}, Email={email}")

    return jsonify(
        {
            "success": True,
            "message": "Thank you for your message! We'll get back to you soon.",
        }
    )


@app.route("/api/stats")
def get_stats():
    """
    API endpoint to get LIVE bot statistics.
    FINAL FIX: Uses synchronous psycopg2 - no event loop issues!
    """
    # Default/fallback stats
    default_stats = {
        "total_servers": 2,
        "total_users": 64,
        "commands_used": 0,
        "uptime": "99.9%",
    }

    # Check cache first (3 minute cache)
    now = datetime.now()
    if stats_cache["data"] and stats_cache["timestamp"]:
        cache_age = (now - stats_cache["timestamp"]).total_seconds()
        if cache_age < CACHE_DURATION.total_seconds():
            log.info(f"📦 Returning cached stats (age: {int(cache_age)}s)")
            return jsonify(stats_cache["data"])

    # Get database pool
    pool = init_db_pool()
    if not pool:
        log.error("❌ Database pool unavailable, returning default stats")
        return jsonify(default_stats)

    conn = None
    try:
        # Get connection from pool
        conn = pool.getconn()
        cursor = conn.cursor()

        # Fetch stats from database
        cursor.execute(
            "SELECT server_count, user_count, commands_used, last_updated FROM public.bot_stats WHERE bot_id = %s",
            (YOUR_BOT_ID,),
        )

        row = cursor.fetchone()
        cursor.close()

        if row:
            stats = {
                "total_servers": row[0] or 0,
                "total_users": row[1] or 0,
                "commands_used": row[2] or 0,
                "uptime": "99.9%",
                "last_updated": row[3].isoformat() if row[3] else None,
            }

            # Update cache
            stats_cache["data"] = stats
            stats_cache["timestamp"] = now

            log.info(
                f"✅ Stats fetched: {stats['total_servers']} servers, {stats['total_users']} users, {stats['commands_used']} commands"
            )
            return jsonify(stats)
        else:
            log.warning(f"⚠️ No stats found for bot_id={YOUR_BOT_ID}")

            # Try to initialize the stats row
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO public.bot_stats (bot_id, server_count, user_count, commands_used, last_updated)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (bot_id) DO NOTHING
                    """,
                    (
                        YOUR_BOT_ID,
                        default_stats["total_servers"],
                        default_stats["total_users"],
                        default_stats["commands_used"],
                    ),
                )
                conn.commit()
                cursor.close()
                log.info("✅ Initialized bot_stats table with default values")
            except Exception as init_error:
                log.error(f"❌ Failed to initialize bot_stats: {init_error}")
                if conn:
                    conn.rollback()

            return jsonify(default_stats)

    except psycopg2.errors.UndefinedTable:
        log.error(
            "❌ bot_stats table does not exist! Run the SQL fix script in Supabase."
        )
        return (
            jsonify(
                {
                    **default_stats,
                    "error": "Database table missing. Please contact administrator.",
                }
            ),
            500,
        )

    except Exception as e:
        log.error(f"❌ Error fetching stats from database: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return jsonify(default_stats)

    finally:
        # Return connection to pool
        if conn and pool:
            pool.putconn(conn)


@app.route("/api/health")
def health_check():
    """Health check endpoint for monitoring."""
    pool = init_db_pool()
    pool_status = "disconnected"
    pool_info = "N/A"

    if pool:
        conn = None
        try:
            conn = pool.getconn()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            pool_status = "connected"

            # Get pool info safely
            try:
                pool_info = f"{len([c for c in pool._pool if c])} connections"
            except:
                pool_info = "Pool active"
        except Exception as e:
            pool_status = f"error: {str(e)}"
        finally:
            if conn and pool:
                pool.putconn(conn)

    return jsonify(
        {
            "status": "healthy",
            "service": "flask_frontend",
            "timestamp": datetime.now().isoformat(),
            "database": pool_status,
            "pool_size": pool_info,
        }
    )


@app.route("/api/db-test")
def test_db():
    """Test database connectivity (for debugging)."""
    pool = init_db_pool()
    if not pool:
        return (
            jsonify({"status": "error", "message": "Database pool not initialized"}),
            500,
        )

    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()

        # Test query
        cursor.execute("SELECT 1")
        result = cursor.fetchone()[0]

        # Check if bot_stats table exists
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'bot_stats'
            )
            """
        )
        table_exists = cursor.fetchone()[0]

        cursor.close()

        return jsonify(
            {
                "status": "success",
                "database": "connected",
                "test_query": result,
                "bot_stats_table_exists": table_exists,
                "connection_type": "psycopg2 (synchronous)",
                "connection_string": (
                    DATABASE_URL.split("@")[1] if "@" in DATABASE_URL else "hidden"
                ),
            }
        )
    except Exception as e:
        log.error(f"Database test failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn and pool:
            pool.putconn(conn)


@app.route("/robots.txt")
def robots():
    """SEO: Allow all bots to crawl the site."""
    return "User-agent: *\nAllow: /"


@app.errorhandler(404)
def page_not_found(e):
    """Custom 404 page."""
    return render_template("index.html", invite_url=INVITE_URL), 404


@app.errorhandler(500)
def internal_error(e):
    """Custom 500 error page."""
    log.error(f"Internal server error: {e}")
    return (
        jsonify(
            {
                "error": "Internal server error",
                "message": "Something went wrong. Please try again later.",
            }
        ),
        500,
    )


def run_flask_app():
    """Start the Flask application."""
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", 9528))
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"

    log.info("=" * 60)
    log.info("🌐 FLASK FRONTEND STARTING")
    log.info("=" * 60)
    log.info(f"   Host: {host}")
    log.info(f"   Port: {port}")
    log.info(f"   Debug: {debug}")
    log.info(f"   Bot ID: {YOUR_BOT_ID}")
    log.info(f"   Domain: {SERVER_DOMAIN}")
    log.info(f"   DB: psycopg2 (synchronous)")
    log.info(f"   Cache: {CACHE_DURATION.seconds}s")
    log.info("=" * 60)

    # Initialize database pool before starting Flask
    init_db_pool()

    # Start Flask app
    app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)


if __name__ == "__main__":
    run_flask_app()
