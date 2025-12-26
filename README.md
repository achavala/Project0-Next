# Mike Agent v3 - RL Trading Bot

Autonomous reinforcement learning agent for SPY 0DTE options trading with 13 institutional-grade safeguards.

**100% Local Execution** - All trading, data, and dashboards run on your machine.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API Keys
Copy the example config and add your Alpaca keys:
```bash
cp config.py.example config.py
```

Edit `config.py`:
```python
ALPACA_KEY = "your_key_here"
ALPACA_SECRET = "your_secret_here"
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"  # Paper trading
# ALPACA_BASE_URL = "https://api.alpaca.markets"  # Live trading
```

### 3. Run the Agent
```bash
# Start the live trading agent
python mike_agent_live_safe.py

# Or use the watchdog (auto-restarts during market hours)
./start_live_agent_with_watchdog.sh
```

### 4. Start the Dashboard
```bash
# In a separate terminal
streamlit run app.py
```

Dashboard will be available at: `http://localhost:8501`

---

## 📊 Components

### Core Trading Agent
- **`mike_agent_live_safe.py`** - Main production trading agent
- **`mike_rl_agent.py`** - RL model training and backtesting

### Dashboards
- **`app.py`** - Main Streamlit dashboard
- **`dashboard_app.py`** - Alternative dashboard

### Scripts
- **`start_live_agent_with_watchdog.sh`** - Start agent with auto-restart
- **`start_dashboard.sh`** - Start dashboard
- **`start_paper_trading.sh`** - Start paper trading mode

---

## 🛡️ Safeguards (13 Total)

| Safeguard | Value | Description |
|-----------|-------|-------------|
| Daily Loss Limit | -15% | Max daily loss before stopping |
| Position Size | 25% | Max equity per position |
| VIX Kill Switch | >28 | Stop trading in high volatility |
| IV Rank Minimum | 30% | Minimum implied volatility |
| Time Filter | 2:30 PM | No new entries after |
| Max Drawdown | -30% | Max drawdown from peak |
| Max Notional | $50k | Max per order |
| Hard Stop | -15% | Fixed stop-loss |
| TP1 | +40% | First take-profit level |
| TP2 | +60% | Second take-profit level |
| TP3 | +100% | Third take-profit level |
| Trailing Stop | After TP4 | Dynamic trailing stop |
| Duplicate Protection | 5 min | Order cooldown |

---

## 🧪 Training & Backtesting

### Train a New Model
```bash
python mike_rl_agent.py --train
```

### Run Backtest
```bash
python backtest_mike_agent_v3.py --start 2025-01-01 --end 2025-12-01
```

### Validate Model
```bash
python validate_model.py --model models/mike_momentum_model_v2_intraday_full.zip
```

---

## 📁 Directory Structure

```
Project0-Next/
├── mike_agent_live_safe.py     # Main trading agent
├── mike_rl_agent.py            # RL training
├── app.py                      # Streamlit dashboard
├── config.py                   # API keys (create from .example)
├── models/                     # Trained RL models
│   └── mike_momentum_model_v2_intraday_full.zip
├── core/                       # Core modules
├── gui_v2/                     # GUI components
└── logs/                       # Trading logs
```

---

## 🔧 Available Scripts

| Script | Purpose |
|--------|---------|
| `start_live_agent_with_watchdog.sh` | Start agent with auto-restart |
| `start_dashboard.sh` | Start Streamlit dashboard |
| `start_paper_trading.sh` | Start in paper mode |
| `start_training.sh` | Start model training |
| `run_backtest.sh` | Run backtesting |

---

## 📈 Monitoring

### View Live Logs
```bash
# Agent logs
tail -f logs/live_agent_$(date +%Y%m%d).log

# Or agent output
tail -f agent_output.log
```

### Check Agent Status
```bash
python check_agent_status.py
```

### View Dashboard
Open `http://localhost:8501` after running `streamlit run app.py`

---

## ⚙️ Configuration

### Paper Trading (Default)
```python
# config.py
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
```

### Live Trading
```python
# config.py
ALPACA_BASE_URL = "https://api.alpaca.markets"
```

---

## 🎯 Models Available

| Model | Description |
|-------|-------------|
| `mike_momentum_model_v2_intraday_full.zip` | Production model (500K steps) |
| `mike_23feature_model_final.zip` | 23-feature model |
| `mike_momentum_model_v3_lstm.zip` | LSTM-based model |

---

## 📝 Requirements

- Python 3.10+
- Apple Silicon or x86 (tested on M1/M2/M3)
- Alpaca account (paper or live)
- ~8GB RAM recommended

---

## 🔒 Security Notes

- Never commit `config.py` to git (it's in `.gitignore`)
- Use paper trading until you're confident
- Start with small position sizes
- Monitor closely during first few trading sessions

---

Built December 2025 on Apple Silicon.
# Project0-Next
