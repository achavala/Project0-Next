#!/bin/bash
# =============================================================================
# Mike Agent v3 - Local Quick Start
# Starts both the trading agent and dashboard locally
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 MIKE AGENT v3 - LOCAL QUICK START"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Set timezone
export TZ=America/New_York
echo "🕐 Timezone: $TZ (EST/EDT)"
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "📦 Activating virtual environment..."
    source venv/bin/activate
    echo "✅ Virtual environment activated"
fi

# Check config
if [ ! -f "config.py" ]; then
    echo "❌ config.py not found!"
    echo "   Copy config.py.example to config.py and add your API keys:"
    echo "   cp config.py.example config.py"
    exit 1
fi

# Check for required dependencies
echo ""
echo "🔍 Checking dependencies..."
if ! python -c "import alpaca_trade_api" 2>/dev/null; then
    echo "⚠️  alpaca-trade-api not found. Installing dependencies..."
    pip install -r requirements.txt
fi
echo "✅ Dependencies OK"

# Create logs directory
mkdir -p logs

# Kill any existing processes
echo ""
echo "🧹 Cleaning up existing processes..."
pkill -f "mike_agent_live_safe.py" 2>/dev/null || true
lsof -ti:8501 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 2
echo "✅ Cleanup complete"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 STARTING COMPONENTS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Start dashboard in background
echo "📊 Starting Streamlit dashboard..."
streamlit run app.py --server.port 8501 --server.headless true &
DASHBOARD_PID=$!
sleep 3

if kill -0 $DASHBOARD_PID 2>/dev/null; then
    echo "✅ Dashboard running at: http://localhost:8501"
else
    echo "⚠️  Dashboard may have failed to start"
fi

# Start agent
echo ""
echo "🤖 Starting trading agent..."
echo "   Logs: logs/live_agent_$(date +%Y%m%d).log"
echo ""

LOG_FILE="logs/live_agent_$(date +%Y%m%d).log"
python -u mike_agent_live_safe.py 2>&1 | tee -a "$LOG_FILE" &
AGENT_PID=$!
sleep 5

if kill -0 $AGENT_PID 2>/dev/null; then
    echo "✅ Agent running (PID: $AGENT_PID)"
else
    echo "⚠️  Agent may have failed to start. Check logs."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ MIKE AGENT RUNNING LOCALLY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 Dashboard: http://localhost:8501"
echo "📋 Agent PID: $AGENT_PID"
echo "📁 Logs: $LOG_FILE"
echo ""
echo "To stop everything:"
echo "  pkill -f mike_agent_live_safe.py"
echo "  lsof -ti:8501 | xargs kill -9"
echo ""
echo "To view logs:"
echo "  tail -f $LOG_FILE"
echo ""

# Function to handle shutdown
cleanup() {
    echo ""
    echo "🛑 Shutting down..."
    kill $AGENT_PID 2>/dev/null || true
    kill $DASHBOARD_PID 2>/dev/null || true
    echo "✅ Stopped"
    exit 0
}

trap cleanup SIGTERM SIGINT

# Keep script running - wait for agent
echo "Press Ctrl+C to stop all components"
echo ""
wait $AGENT_PID

