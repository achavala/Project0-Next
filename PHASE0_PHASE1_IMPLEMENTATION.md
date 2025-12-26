# Phase 0 & Phase 1 Implementation

## Executive Summary

Based on the 4-architect review feedback, this document outlines the changes made to address the core issue:

> "You are optimizing directional correctness in a market where directional correctness is secondary."

In 0-DTE options:
- **What matters most**: Gamma/vanna flows, IV term structure, liquidity, expected move
- **What we were doing**: RSI, MACD, EMA (lagging duplicates of price)

---

## Phase 0: STOP THE BLEEDING ✅ COMPLETE

All Phase 0 changes are **non-ML** hard gates that block trades unconditionally.

### 1. ✅ Remove Resampling Entirely
- **File**: `mike_agent_live_safe.py`
- **Line**: ~4417
- **Change**: `resampled = False` is now hard-coded
- **Reason**: "Kill the idea that more trades = learning"

### 2. ✅ Enforce Single Live Trading Instance
- **File**: `mike_agent_live_safe.py`
- **Function**: `run_safe_live_trading()`
- **Change**: Added PID-based lock file check at startup
- **Lock files**: `/tmp/mike_agent_live.lock`, `/tmp/mike_agent_live.pid`
- **Behavior**: Agent exits with error if another instance is running

### 3. ✅ Block Trades When Spread > 15% of Premium
- **File**: `mike_agent_live_safe.py`
- **Function**: `check_order_safety()`
- **Thresholds**: 
  - Max 15% of mid-price (down from 20%)
  - Max $0.10 absolute spread
- **Reason**: "Most 0-DTE losses occur when liquidity evaporates"

### 4. ✅ Block Trades When Quote Age > 5 Seconds
- **File**: `mike_agent_live_safe.py`
- **Function**: `check_order_safety()`
- **Threshold**: 5 seconds max quote age
- **Reason**: "Stale quotes kill 0-DTE traders"

### 5. ✅ Block Trades When Expected Move < 1.2x Breakeven
- **File**: `mike_agent_live_safe.py`
- **Function**: `check_order_safety()`
- **Threshold**: Expected move must be >= 1.2x breakeven (20% edge required)
- **Reason**: "This single rule would eliminate most losses"

### 6. ✅ Disable SPX, IWM - Only SPY/QQQ Allowed
- **File**: `mike_agent_live_safe.py`
- **Change**: `TRADING_SYMBOLS = ['SPY', 'QQQ']`
- **Blocked**: `BLOCKED_SYMBOLS = ['SPX', 'IWM', '^SPX', 'SPXW']`
- **Reason**: SPX not available in paper trading, IWM has lower liquidity

### 7. ✅ Raise Confidence Threshold to 0.70
- **File**: `mike_agent_live_safe.py`
- **Change**: `MIN_ACTION_STRENGTH_THRESHOLD = 0.70` (up from 0.60)
- **Reason**: "The model is correctly uncertain - do NOT lower threshold"

---

## Phase 1: STRUCTURAL EDGE ✅ COMPLETE

Phase 1 adds new indicators and changes ensemble behavior without model retraining.

### 1. ✅ VIX1D Indicator
- **File**: `phase0_gates.py`
- **Class**: `Phase1Indicators.get_vix1d()`
- **Source**: Polygon API for `I:VIX1D`, falls back to VIX
- **Reason**: "VIX (30-day) is useless for 30-minute options"

### 2. ✅ IV Rank / Skew Indicators
- **File**: `phase0_gates.py`
- **Class**: `Phase1Indicators.get_iv_rank()`, `get_iv_skew()`
- **Calculation**: Percentile of current IV vs 252-day historical
- **Thresholds**: Low (<20), High (>80)

### 3. ✅ Expected Move Calculation
- **File**: `phase0_gates.py`
- **Function**: `Phase1Indicators.calculate_expected_move()`
- **Formula**: `Price * IV * sqrt(T/365)` adjusted for intraday
- **Also in**: `mike_agent_live_safe.py` `check_order_safety()`

### 4. ✅ Gamma Wall Proxy
- **File**: `phase0_gates.py`
- **Class**: `Phase1Indicators.get_gamma_wall_levels()`
- **Note**: Placeholder - requires options chain OI data for full implementation

### 5. ✅ Convert Ensemble from Averaging → Gating
- **File**: `multi_agent_ensemble.py`
- **Function**: `MetaPolicyRouter.route()`
- **Change**: `USE_GATING_ENSEMBLE = True`

**Problem with averaging:**
```
Trend agent: 0.8 BUY
Reversal agent: 0.2 SELL
Average: 0.5 DO NOTHING
Result: Miss both breakouts AND ranges
```

**Solution (gating):**
- Detect regime first
- Select appropriate agent(s)
- IGNORE conflicting agents

**Regime-based selection:**
| Regime | Agent Selected | Agents Ignored |
|--------|----------------|----------------|
| CHAOS (VIX>25) | NONE | ALL |
| VOLATILE/STORM | Volatility | Trend, Reversal |
| TRENDING | Trend | Reversal |
| MEAN_REVERTING | Reversal | Trend |
| CALM (VIX<12) | Vol Breakout OR Reversal | Trend |

### 6. ✅ Liquidity & Volatility Agents as Hard Vetoes
- **File**: `multi_agent_ensemble.py`
- **Function**: `MetaPolicyRouter.route()`
- **Vetoes**:
  - Delta hedging agent can VETO entries (if conf > 0.8)
  - Gamma agent penalizes confidence (if conf < 0.3)

### 7. ✅ Restrict RL to Timing/Sizing/Exit Only
- **File**: `mike_agent_live_safe.py`
- **Section**: RL + Ensemble combination logic

**Old approach (wrong):**
```python
RL_WEIGHT = 0.40
ENSEMBLE_WEIGHT = 0.60
```

**New approach (Phase 1):**
```python
RL_ENTRY_WEIGHT = 0.0    # RL has NO WEIGHT for entry direction
ENSEMBLE_ENTRY_WEIGHT = 1.0  # Ensemble decides entries
RL_EXIT_WEIGHT = 0.6    # RL is still good at exits
ENSEMBLE_EXIT_WEIGHT = 0.4
```

**RL Role in Phase 1:**
| Decision Type | RL Role |
|---------------|---------|
| Entry Direction | ❌ NONE (Ensemble only) |
| Entry Timing | ✅ Can refine timing |
| Position Sizing | ✅ Can adjust size |
| Exit Timing | ✅ Strong fit |
| Exit Decision | ✅ Can trigger exits |

---

## Files Modified

| File | Changes |
|------|---------|
| `mike_agent_live_safe.py` | Phase 0 gates, single instance lock, RL restrictions |
| `multi_agent_ensemble.py` | Gating ensemble, hard vetoes |
| `phase0_gates.py` | **NEW** - Phase 0/1 gates, indicators, ensemble classes |

---

## Testing the Changes

### 1. Test Single Instance Lock
```bash
# Terminal 1: Start agent
python mike_agent_live_safe.py

# Terminal 2: Try to start another (should fail)
python mike_agent_live_safe.py
# Expected: "❌ PHASE 0: SINGLE INSTANCE VIOLATION DETECTED"
```

### 2. Test Phase 0 Gates
```bash
python phase0_gates.py
# Runs self-tests for all gates
```

### 3. Monitor Gate Blocks
Look for these log messages:
- `⛔ P0-GATE: Spread too wide`
- `⛔ P0-GATE: Quote too stale`
- `⛔ P0-GATE: No edge - Expected move < breakeven`
- `⛔ P0-GATE: Low option volume`
- `⛔ P0-GATE: Low open interest`

### 4. Monitor Ensemble Gating
Look for these log messages:
- `🎯 Entry Signal: Ensemble=BUY_CALL (conf=X.XX) | RL demoted per Phase 1`
- `⚠️ RL VETO: RL says HOLD vs Ensemble says BUY_CALL`
- Regime changes: `regime=TREND`, `regime=MEAN_REVERTING`, etc.

---

## Expected Impact

### What Will Change
1. **Fewer trades** - Higher threshold, stricter gates
2. **No forced trades** - Resampling removed
3. **Better trade quality** - Expected move edge required
4. **Regime-appropriate signals** - Gating prevents conflicting signals
5. **No RL-driven entries** - Ensemble only for direction

### What We Expect
- Confidence plateaus around 0.50 should now result in HOLD (not trades)
- Trades that "look right" but die immediately should be blocked
- Stop-losses firing instantly should be prevented by expected move gate
- Overall profitability should improve even with fewer trades

---

## Next Steps (Not Implemented Yet)

### Phase 2: Model Retraining
1. Retrain RL model with new features (VIX1D, IV rank, gamma)
2. Add options-specific features (bid/ask spread, quote age, greeks)
3. Train on realistic transaction costs

### Phase 3: Execution Optimization
1. Implement queue priority modeling
2. Add partial fill handling
3. Implement IV crush detection
4. Add gap risk modeling

---

## Architect Review Summary

| Issue | Status |
|-------|--------|
| Directional optimization wrong for 0-DTE | ✅ Addressed with expected move gate |
| RL confidence hovers ~0.50 | ✅ Raised threshold, RL demoted for entries |
| Resampling forces trades | ✅ Removed |
| Ensemble averages conflicting signals | ✅ Changed to gating |
| Missing VIX1D, IV rank | ✅ Added in phase0_gates.py |
| Missing expected move vs breakeven | ✅ Added as hard gate |
| Liquidity not checked | ✅ Added volume + OI gates |
| Multiple instances possible | ✅ Single instance lock added |

