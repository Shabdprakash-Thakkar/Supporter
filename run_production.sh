#!/bin/bash
# File: Discord_BOT/Tester/run_production.sh

echo "============================================================"
echo "🚀 SUPPORTER BOT - PRODUCTION STARTUP"
echo "============================================================"
echo ""

# Change to correct directory
cd "$(dirname "$0")"

# Set Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/Python_Files"

# Install/Update packages
echo "📦 Checking Python packages..."
pip install -r Data_Files/requirements.txt --quiet

echo ""
echo "============================================================"
echo "✅ STARTING FULL APPLICATION"
echo "============================================================"
echo ""
echo "🤖 Discord Bot: Starting..."
echo "🌐 Flask Frontend: Starting on port 9528..."
echo "🌍 Domain: https://shabdprakash-thakkar.online"
echo ""

# Run the bot
python run_full_app.py