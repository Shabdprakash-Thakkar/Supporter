#!/usr/bin/env python3
"""
LOCALHOST DEVELOPMENT RUNNER
Runs both Discord Bot and Flask Frontend on localhost:5000
"""

import sys
import os
import multiprocessing
import time
from pathlib import Path

# Add Python_Files and Flask_Frontend directories to path
BASE_DIR = Path(__file__).parent.resolve()
PYTHON_FILES_DIR = BASE_DIR / "Python_Files"
FLASK_DIR = BASE_DIR / "Flask_Frontend"

sys.path.insert(0, str(PYTHON_FILES_DIR))
sys.path.insert(0, str(FLASK_DIR))

# Read from .env file
SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
SERVER_PORT = os.getenv("FLASK_PORT", "5000")
SERVER_DOMAIN = os.getenv("SERVER_DOMAIN", "http://localhost:5000")


def run_discord_bot():
    """Run the Discord bot in a separate process"""
    print("\n" + "=" * 60)
    print(" STARTING DISCORD BOT (LOCALHOST)")
    print("=" * 60 + "\n")

    try:
        import supporter
        supporter.run_bot()
    except KeyboardInterrupt:
        print("\n›' Discord bot stopped by user")
    except Exception as e:
        print(f"\n Discord bot error: {e}")
        import traceback
        traceback.print_exc()


def run_flask_frontend():
    """Run the Flask frontend in a separate process"""
    print("\n" + "=" * 60)
    print(" STARTING FLASK FRONTEND (LOCALHOST)")
    print("=" * 60)
    print(f" Server IP: {SERVER_IP}")
    print(f"Port: {SERVER_PORT}")
    print(f"Local URL: {SERVER_DOMAIN}")
    print("=" * 60 + "\n")

    time.sleep(2)

    try:
        import app
        app.run_flask_app()
    except KeyboardInterrupt:
        print("\n›' Flask frontend stopped by user")
    except Exception as e:
        print(f"\n Flask frontend error: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main function to start both services in localhost mode"""
    print("\n" + "=" * 60)
    print(" SUPPORTER BOT - LOCALHOST DEVELOPMENT")
    print("=" * 60)
    print("\n   Server Configuration:")
    print(f"    IP Address: {SERVER_IP}")
    print(f"    Port: {SERVER_PORT}")
    print(f"    URL: {SERVER_DOMAIN}")
    print("    Environment: Development (Localhost)")
    print("\n Starting both Discord Bot and Flask Frontend...")
    print("  Press Ctrl+C to stop all services\n")

    # Verify required directories exist
    if not PYTHON_FILES_DIR.exists():
        print(f" ERROR: Python_Files directory not found at {PYTHON_FILES_DIR}")
        sys.exit(1)

    if not FLASK_DIR.exists():
        print(f" ERROR: Flask_Frontend directory not found at {FLASK_DIR}")
        sys.exit(1)

    # Create processes for both services
    discord_process = multiprocessing.Process(
        target=run_discord_bot, name="DiscordBot-Localhost"
    )
    flask_process = multiprocessing.Process(
        target=run_flask_frontend, name="FlaskFrontend-Localhost"
    )

    try:
        # Start both processes
        discord_process.start()
        flask_process.start()

        print("\n" + "=" * 60)
        print(" BOTH SERVICES STARTED SUCCESSFULLY!")
        print("=" * 60)
        print("\n Discord Bot: Running")
        print(f" Flask Frontend: {SERVER_DOMAIN}")
        print(f"\n Open your browser and go to: {SERVER_DOMAIN}")
        print(" Dashboard login: {SERVER_DOMAIN}/dashboard")
        print("  IMPORTANT: Update Discord OAuth2 redirect URI to:")
        print(f"   {SERVER_DOMAIN}/dashboard/callback")
        print("\n  Press Ctrl+C to stop\n")

        # Wait for both processes
        discord_process.join()
        flask_process.join()

    except KeyboardInterrupt:
        print("\n\n" + "=" * 60)
        print(" SHUTTING DOWN ALL SERVICES...")
        print("=" * 60)

        if discord_process.is_alive():
            print("  Stopping Discord bot...")
            discord_process.terminate()
            discord_process.join(timeout=5)
            if discord_process.is_alive():
                print("  Force killing Discord bot...")
                discord_process.kill()

        if flask_process.is_alive():
            print("  Stopping Flask frontend...")
            flask_process.terminate()
            flask_process.join(timeout=5)
            if flask_process.is_alive():
                print("  Force killing Flask frontend...")
                flask_process.kill()

        print("\n All services stopped successfully!")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

        if discord_process.is_alive():
            discord_process.terminate()
        if flask_process.is_alive():
            flask_process.terminate()

        sys.exit(1)

    finally:
        if discord_process.is_alive():
            discord_process.kill()
        if flask_process.is_alive():
            flask_process.kill()


if __name__ == "__main__":
    multiprocessing.freeze_support()

    print("=" * 60)
    print(" LOCALHOST DEVELOPMENT MODE")
    print("=" * 60)

    main()