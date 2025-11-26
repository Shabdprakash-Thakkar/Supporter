"""
PRODUCTION RUNNER
Python-only entry point that runs both Discord Bot and Flask Frontend
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

# Add to Python path
sys.path.insert(0, str(PYTHON_FILES_DIR))
sys.path.insert(0, str(FLASK_DIR))

# Read from .env file
SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1") # Use actual server IP in production
SERVER_PORT = os.getenv("FLASK_PORT", "5000") # Use desired port in production
SERVER_DOMAIN = os.getenv("SERVER_DOMAIN", "http://localhost") # Use actual domain in production


def run_discord_bot():
    """Run the Discord bot in a separate process"""
    print("\n" + "=" * 20)
    print("🤖 STARTING DISCORD BOT (PRODUCTION)")
    print("=" * 20 + "\n")

    try:
        # Import after path is set
        import supporter

        supporter.run_bot()
    except KeyboardInterrupt:
        print("\n🛑 Discord bot stopped by user")
    except Exception as e:
        print(f"\n❌ Discord bot error: {e}")
        import traceback

        traceback.print_exc()


def run_flask_frontend():
    """Run the Flask frontend in a separate process"""
    print("\n" + "=" * 20)
    print("🌐 STARTING FLASK FRONTEND (PRODUCTION)")
    print("=" * 20)
    print(f"📍 Server IP: {SERVER_IP}")
    print(f"🔌 Port: {SERVER_PORT}")
    print(f"🌍 Domain: {SERVER_DOMAIN}")
    print("=" * 20 + "\n")

    time.sleep(2)

    try:
        # Import after path is set
        import app

        app.run_flask_app()
    except KeyboardInterrupt:
        print("\n🛑 Flask frontend stopped by user")
    except Exception as e:
        print(f"\n❌ Flask frontend error: {e}")
        import traceback

        traceback.print_exc()


def main():
    """Main function to start both services in production mode"""
    print("\n" + "=" * 20)
    print("🚀 SUPPORTER BOT - PRODUCTION DEPLOYMENT")
    print("=" * 20)
    print("\n📦 Server Configuration:")
    print(f"   • IP Address: {SERVER_IP}")
    print(f"   • Port: {SERVER_PORT}")
    print(f"   • Domain: {SERVER_DOMAIN}")
    print("    • Environment: Production")
    print("\n🔄 Starting both Discord Bot and Flask Frontend...")
    print("⌨️  Press Ctrl+C to stop all services\n")

    # Verify required directories exist
    if not PYTHON_FILES_DIR.exists():
        print(f"❌ ERROR: Python_Files directory not found at {PYTHON_FILES_DIR}")
        print("   Please check your file structure!")
        sys.exit(1)

    if not FLASK_DIR.exists():
        print(f"❌ ERROR: Flask_Frontend directory not found at {FLASK_DIR}")
        print("   Please check your file structure!")
        sys.exit(1)

    # Create processes for both services
    discord_process = multiprocessing.Process(
        target=run_discord_bot, name="DiscordBot-Production"
    )
    flask_process = multiprocessing.Process(
        target=run_flask_frontend, name="FlaskFrontend-Production"
    )

    try:
        discord_process.start()
        flask_process.start()

        print("\n" + "=" * 20)
        print("✅ BOTH SERVICES STARTED SUCCESSFULLY!")
        print("=" * 20)
        print("\n🤖 Discord Bot: Running")
        print(f"🌐 Flask Frontend: https://{SERVER_IP}:{SERVER_PORT}")
        print(f"🌍 Public Domain: {SERVER_DOMAIN}")
        print("\n💡 Both services are now running in production mode!")
        print("⏰ Server will keep running until stopped manually\n")

        # Wait for both processes
        discord_process.join()
        flask_process.join()

    except KeyboardInterrupt:
        print("\n\n" + "=" * 20)
        print("🛑 SHUTTING DOWN ALL SERVICES...")
        print("=" * 20)

        # Terminate both processes gracefully
        if discord_process.is_alive():
            print("⏹️  Stopping Discord bot...")
            discord_process.terminate()
            discord_process.join(timeout=5)
            if discord_process.is_alive():
                print("⚠️  Force killing Discord bot...")
                discord_process.kill()

        if flask_process.is_alive():
            print("⏹️  Stopping Flask frontend...")
            flask_process.terminate()
            flask_process.join(timeout=5)
            if flask_process.is_alive():
                print("⚠️  Force killing Flask frontend...")
                flask_process.kill()

        print("\n✅ All services stopped successfully!")
        print("=" * 20 + "\n")

    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback

        traceback.print_exc()

        # Clean up processes on error
        if discord_process.is_alive():
            print("🔧 Cleaning up Discord bot process...")
            discord_process.terminate()
        if flask_process.is_alive():
            print("🔧 Cleaning up Flask frontend process...")
            flask_process.terminate()

        sys.exit(1)

    finally:
        # Final cleanup - ensure all processes are terminated
        if discord_process.is_alive():
            discord_process.kill()
        if flask_process.is_alive():
            flask_process.kill()


if __name__ == "__main__":
    multiprocessing.freeze_support()

    print("=" * 20)
    print("🎯 PRODUCTION MODE ACTIVATED")
    print("=" * 20)

    main()
