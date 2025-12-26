# 📊 Chart Data Sources - Complete Reference

**Date:** December 26, 2025  
**Dashboard:** http://localhost:8501

---

## 📈 CHART 1: SPY Current Market Chart

### **Location:** `app.py` line 381
```python
fig = create_simple_candlestick(spy_data, "SPY - Current")
```

### **Data Source:**
- **Function:** `get_live_data_for_prediction("SPY", bars=100)` (line 36)
- **Priority Order:**
  1. **Massive API** (Primary - Real-Time) - `massive_client.get_historical_data(symbol, today_str, end_date_str, interval='1m')`
  2. **Alpaca API** (Fallback) - `api.get_bars(symbol, '1Min', start=today_str, limit=bars)`
  3. **yfinance** (Last Resort) - `ticker.history(period="1d", interval="1m")`

### **Data Details:**
- **Bars:** Last 50 candles (from 100 fetched, `.tail(50)` used in chart)
- **Interval:** 1-minute bars
- **Timeframe:** Today's data (period="1d")
- **Timezone:** Converted to EST
- **Caching:** ❌ **NO CACHING** - Fresh data on every dashboard refresh

### **Storage:**
- ❌ Not stored persistently
- ✅ Stored in memory during dashboard session (`spy_data` variable)

---

## 📈 CHART 2: QQQ Current Market Chart

### **Location:** `app.py` line 385
```python
fig = create_simple_candlestick(qqq_data, "QQQ - Current")
```

### **Data Source:**
- **Function:** `get_live_data_for_prediction("QQQ", bars=100)` (line 271)
- **Priority Order:**
  1. **Massive API** (Primary - Real-Time) - `massive_client.get_historical_data(symbol, today_str, end_date_str, interval='1m')`
  2. **Alpaca API** (Fallback) - `api.get_bars(symbol, '1Min', start=today_str, limit=bars)`
  3. **yfinance** (Last Resort) - `ticker.history(period="1d", interval="1m")`

### **Data Details:**
- **Bars:** Last 50 candles (from 100 fetched, `.tail(50)` used in chart)
- **Interval:** 1-minute bars
- **Timeframe:** Today's data (period="1d")
- **Timezone:** Converted to EST
- **Caching:** ❌ **NO CACHING** - Fresh data on every dashboard refresh

### **Storage:**
- ❌ Not stored persistently
- ✅ Stored in memory during dashboard session (`qqq_data` variable)

---

## 🔮 CHART 3: SPY Prediction Chart (Last 20 + Next 20 Candles)

### **Location:** `app.py` line 395
```python
fig = create_prediction_candlestick(spy_data, spy_predictions, "SPY")
```

### **Historical Data (Last 20 Candles):**
- **Source:** Same as Chart 1 (`spy_data`)
- **Bars Used:** Last 20 candles (`.tail(20)`)
- **Data Source:** Massive API → Alpaca API → yfinance (fallback chain)

### **Predicted Data (Next 20 Candles):**
- **Source:** `predictor.predict(spy_data, "SPY")` (line 294)
- **Model:** Transformer-based price predictor (`price_predictor.py`)
- **Input:** Last 20 candles from `spy_data`
- **Output:** 20 predicted OHLCV candles
- **Model Location:** `models/predictor/transformer_model.pt`

### **Storage:**
- ✅ **Predictions Logged:** `logs/predictions/prediction_log_YYYYMMDD.txt`
- ✅ **JSON Storage:** `logs/predictions/predictions_YYYYMMDD.json`
- ✅ **Database:** `logs/predictions/predictions.db` (SQLite)
- ✅ **Model File:** `models/predictor/transformer_model.pt`

---

## 🔮 CHART 4: QQQ Prediction Chart (Last 20 + Next 20 Candles)

### **Location:** `app.py` line 402
```python
fig = create_prediction_candlestick(qqq_data, qqq_predictions, "QQQ")
```

### **Historical Data (Last 20 Candles):**
- **Source:** Same as Chart 2 (`qqq_data`)
- **Bars Used:** Last 20 candles (`.tail(20)`)
- **Data Source:** Massive API → Alpaca API → yfinance (fallback chain)

### **Predicted Data (Next 20 Candles):**
- **Source:** `predictor.predict(qqq_data, "QQQ")` (line 295)
- **Model:** Transformer-based price predictor (`price_predictor.py`)
- **Input:** Last 20 candles from `qqq_data`
- **Output:** 20 predicted OHLCV candles
- **Model Location:** `models/predictor/transformer_model.pt`

### **Storage:**
- ✅ **Predictions Logged:** `logs/predictions/prediction_log_YYYYMMDD.txt`
- ✅ **JSON Storage:** `logs/predictions/predictions_YYYYMMDD.json`
- ✅ **Database:** `logs/predictions/predictions.db` (SQLite)
- ✅ **Model File:** `models/predictor/transformer_model.pt`

---

## 📁 DATA STORAGE LOCATIONS

### **1. Prediction Logs (Text Format)**
**Path:** `/Users/chavala/Project0-Next/logs/predictions/prediction_log_YYYYMMDD.txt`

**Content:**
- Human-readable log of all predictions
- Includes: timestamp, symbol, current price, direction, target, all 20 predicted candles
- Format: Text file with structured sections

**Example:**
```
================================================================================
PREDICTION: SPY_20251226_105723_7166
================================================================================
Time: 2025-12-26T10:57:23
Symbol: SPY
Current Price: $690.24
Direction: BEARISH
Expected Change: -0.19%
Target Price: $688.94

Predicted 20 Candles (T+1 to T+20):
────────────────────────────────────────────────────────────────────────────────
  Candle    Open       High        Low      Close
────────────────────────────────────────────────────────────────────────────────
  T+1       $690.20    $690.35     $690.05  $690.15
  ...
```

---

### **2. Prediction Data (JSON Format)**
**Path:** `/Users/chavala/Project0-Next/logs/predictions/predictions_YYYYMMDD.json`

**Content:**
- Machine-readable JSON format
- All prediction records for the day
- Includes full OHLCV data for all 20 predicted candles

**Structure:**
```json
[
  {
    "id": "SPY_20251226_105723_7166",
    "timestamp": "2025-12-26T10:57:23",
    "symbol": "SPY",
    "current_price": 690.24,
    "predicted_open": [690.20, 690.15, ...],
    "predicted_high": [690.35, 690.30, ...],
    "predicted_low": [690.05, 690.00, ...],
    "predicted_close": [690.15, 690.10, ...],
    "predicted_volume": [1000, 1100, ...],
    "predicted_direction": "BEARISH",
    "predicted_change_pct": -0.19,
    "predicted_target": 688.94
  }
]
```

---

### **3. Prediction Database (SQLite)**
**Path:** `/Users/chavala/Project0-Next/logs/predictions/predictions.db`

**Content:**
- SQLite database with all predictions
- Includes validation results when available
- Queryable for analysis

**Tables:**
- `predictions` - Main prediction records
- Indexes on: timestamp, symbol, validated

**Query Example:**
```sql
SELECT * FROM predictions 
WHERE symbol = 'SPY' 
AND DATE(timestamp) = '2025-12-26'
ORDER BY timestamp DESC;
```

---

### **4. Validation Logs**
**Path:** `/Users/chavala/Project0-Next/logs/predictions/validation_log_YYYYMMDD.txt`

**Content:**
- Detailed validation results
- Candle-by-candle comparison (predicted vs actual)
- Accuracy metrics (MSE, MAE, direction accuracy)

---

### **5. End-of-Day Reports**
**Path:** `/Users/chavala/Project0-Next/logs/predictions/prediction_report_YYYYMMDD.md`

**Content:**
- Markdown format daily summary
- Accuracy metrics
- Performance by symbol
- Detailed prediction table

---

### **6. Model Files**
**Path:** `/Users/chavala/Project0-Next/models/predictor/`

**Files:**
- `transformer_model.pt` - Trained Transformer model weights
- `normalization_params.json` - Feature normalization parameters

---

## 🔄 DATA FLOW DIAGRAM

```
┌─────────────────────────────────────────────────────────────┐
│                    DASHBOARD REFRESH                        │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  get_live_data_for_prediction("SPY", bars=100)              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 1. yfinance.Ticker("SPY").history()                 │  │
│  │    → period="1d", interval="1m"                     │  │
│  │    → Returns: 1-minute bars for today                │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 2. Alpaca API (if yfinance fails)                    │  │
│  │    → api.get_bars("SPY", '1Min', start=today)       │  │
│  └──────────────────────────────────────────────────────┘  │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  spy_data (DataFrame) - Last 100 bars                      │
│  └─> Used for:                                              │
│      • Current Market Chart (last 50 bars)                  │
│      • Prediction Input (last 20 bars)                      │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  predictor.predict(spy_data, "SPY")                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ • Loads model: models/predictor/transformer_model.pt │  │
│  │ • Takes last 20 candles as input                     │  │
│  │ • Generates 20 predicted candles                      │  │
│  └──────────────────────────────────────────────────────┘  │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  spy_predictions (DataFrame) - 20 predicted candles         │
│  └─> Used for:                                              │
│      • Prediction Chart (next 20 candles)                   │
│      • Logging to files                                     │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  pred_logger.log_prediction()                               │
│  └─> Saves to:                                              │
│      • prediction_log_YYYYMMDD.txt                          │
│      • predictions_YYYYMMDD.json                            │
│      • predictions.db (SQLite)                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔍 DATA SOURCE DETAILS

### **yfinance (Primary Source)**
- **Library:** `yfinance` (Yahoo Finance)
- **Method:** `ticker.history(period="1d", interval="1m")`
- **Data Type:** Real-time intraday data
- **Delay:** Typically 15-20 minutes (free tier)
- **Reliability:** High for current day data
- **Rate Limits:** None (but may throttle)

### **Alpaca API (Fallback)**
- **Library:** `alpaca-trade-api`
- **Method:** `api.get_bars(symbol, '1Min', start=today_str, limit=bars)`
- **Data Type:** Real-time market data
- **Delay:** Typically 1-2 minutes (paper trading)
- **Reliability:** High
- **Rate Limits:** Based on subscription tier

---

## ⚠️ IMPORTANT NOTES

1. **No Caching:** Data is fetched fresh on every dashboard refresh
2. **Real-time Updates:** Charts update when you refresh the dashboard
3. **Prediction Storage:** All predictions are logged and stored permanently
4. **Model Persistence:** Trained model is saved and reused across sessions
5. **Data Freshness:** Current market charts show latest available data (may be 15-20 min delayed with yfinance)

---

## 📊 SUMMARY TABLE

| Chart | Data Source | Bars | Storage | Caching |
|-------|-------------|------|---------|---------|
| SPY Current | yfinance → Alpaca | 50 (from 100) | Memory only | ❌ No |
| QQQ Current | yfinance → Alpaca | 50 (from 100) | Memory only | ❌ No |
| SPY Predictions (Historical) | yfinance → Alpaca | 20 | Memory only | ❌ No |
| SPY Predictions (Future) | Transformer Model | 20 | ✅ Multiple files | ✅ Model cached |
| QQQ Predictions (Historical) | yfinance → Alpaca | 20 | Memory only | ❌ No |
| QQQ Predictions (Future) | Transformer Model | 20 | ✅ Multiple files | ✅ Model cached |

---

**Last Updated:** December 26, 2025

