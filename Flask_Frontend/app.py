#!/usr/bin/env python3
"""
Flask Frontend for Supporter Discord Bot
Production-ready version for Wispbyte hosting
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Load environment variables
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "Data_Files")
load_dotenv(os.path.join(DATA_DIR, ".env"))

# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
CORS(app)

# Discord Bot Invite URL
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_PERMISSIONS = os.getenv("DISCORD_PERMISSIONS")
DISCORD_INVITE_URL = f"https://discord.com/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&permissions={DISCORD_PERMISSIONS}&scope=bot+applications.commands"


# Enable CORS with proper configuration
CORS(
    app,
    resources={
        r"/*": {
            "origins": [
                "https://shabdprakash-thakkar.online",
                "http://shabdprakash-thakkar.online",
                "http://194.164.56.165:9528",
                "http://localhost:9528",  # Changed this line to match your production
            ]
        }
    },
)

# ==================== ROUTES ====================


@app.route("/")
def index():
    """Homepage - Bot information with modern Material UI"""
    return render_template("index.html", invite_url=DISCORD_INVITE_URL)


@app.route("/contact")
def contact():
    """Contact page"""
    return render_template("contact.html", invite_url=DISCORD_INVITE_URL)


@app.route("/api/contact", methods=["POST"])
def submit_contact():
    """Handle contact form submission"""
    data = request.get_json()

    # Validate required fields
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    message = data.get("message", "").strip()

    if not all([name, email, message]):
        return jsonify({"success": False, "message": "All fields are required!"}), 400

    # Log the contact form submission
    log.info("=" * 60)
    log.info("📧 CONTACT FORM SUBMISSION")
    log.info("=" * 60)
    log.info(f"Name: {name}")
    log.info(f"Email: {email}")
    log.info(f"Message: {message}")
    log.info("=" * 60)

    return jsonify(
        {
            "success": True,
            "message": "Thank you for your message! We will get back to you soon.",
        }
    )


@app.route("/api/stats")
def get_stats():
    """API endpoint to get bot statistics"""
    # Static stats for now (will add real database queries in Phase 2)
    stats = {
        "total_servers": 3,
        "total_users": 150,
        "commands_used": 1250,
        "uptime": "99.9%",
    }
    return jsonify(stats)


@app.route("/api/health")
def health_check():
    """Health check endpoint"""
    return jsonify(
        {
            "status": "healthy",
            "service": "flask_frontend",
            "message": "Flask frontend is running!",
            "domain": "shabdprakash-thakkar.online",
            "port": os.getenv("FLASK_PORT", "9528"),
        }
    )


@app.route("/robots.txt")
def robots():
    """Robots.txt for SEO"""
    return """User-agent: *
Allow: /
Sitemap: https://shabdprakash-thakkar.online/sitemap.xml"""


# ==================== ERROR HANDLERS ====================


@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors"""
    log.warning(f"404 Error: {request.url}")
    return render_template("index.html"), 404


@app.errorhandler(500)
def internal_error(e):
    """Handle 500 errors"""
    log.error(f"500 Error: {e}")
    return jsonify({"error": "Internal server error"}), 500


# ==================== APP STARTUP ====================


def run_flask_app():
    """Run the Flask application"""
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", 9458))
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"

    log.info("=" * 60)
    log.info("🌐 FLASK FRONTEND STARTING (PRODUCTION)")
    log.info("=" * 60)
    log.info(f"📍 Server: http://{host}:{port}")
    log.info(f"🌍 Domain: https://shabdprakash-thakkar.online")
    log.info(f"🔧 Debug Mode: {debug}")
    log.info("=" * 60)

    try:
        app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)
    except Exception as e:
        log.error(f"❌ Flask error: {e}")
        raise


if __name__ == "__main__":
    run_flask_app()
