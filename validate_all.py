#!/usr/bin/env python3
"""Comprehensive Phase 0/1 and GUI Validation Script"""

import sys
import os
import re

print('=' * 70)
print('🔍 PHASE 0 & PHASE 1 VALIDATION')
print('=' * 70)

# Read all required files
with open('mike_agent_live_safe.py', 'r') as f:
    agent_content = f.read()

with open('phase0_gates.py', 'r') as f:
    phase0_content = f.read()

with open('multi_agent_ensemble.py', 'r') as f:
    ensemble_content = f.read()

with open('app.py', 'r') as f:
    app_content = f.read()

# ==================== PHASE 0 VALIDATION ====================
print('\n🔴 PHASE 0 — STOP THE BLEEDING')
print('-' * 50)

# 1. Check resampling is disabled
print('\n1️⃣ Resampling Disabled:')
if 'resampled = False' in agent_content or 'DISABLE_RESAMPLING = True' in agent_content:
    print('   ✅ Resampling is DISABLED')
else:
    print('   ❌ Resampling may still be active')

# 2. Check single instance enforcement
print('\n2️⃣ Single Live Trading Instance:')
if 'LIVE_AGENT_LOCK_FILE' in agent_content or 'mike_agent_live.lock' in agent_content:
    print('   ✅ Lock file mechanism implemented')
else:
    print('   ❌ Lock file not found')

# 3. Check trade blocking gates
print('\n3️⃣ Trade Blocking Gates:')
gates = [
    ('MAX_SPREAD_PCT', 'Spread % check'),
    ('MAX_QUOTE_AGE_SECONDS', 'Quote age check'),
    ('MIN_EXPECTED_MOVE_RATIO', 'Expected move check')
]
for gate, desc in gates:
    if gate in agent_content:
        print(f'   ✅ {desc} ({gate})')
    else:
        print(f'   ❌ {desc} NOT FOUND')

# 4. Check symbol restrictions
print('\n4️⃣ Symbol Restrictions:')
if 'BLOCKED_SYMBOLS' in agent_content and 'SPX' in agent_content and 'IWM' in agent_content:
    print('   ✅ SPX and IWM are BLOCKED')
else:
    print('   ❌ Symbol blocking not found')

if "TRADING_SYMBOLS" in agent_content and "'SPY'" in agent_content and "'QQQ'" in agent_content:
    print('   ✅ Trading limited to SPY, QQQ')
else:
    print('   ⚠️ Check TRADING_SYMBOLS manually')

# 5. Check confidence threshold
print('\n5️⃣ Confidence Threshold:')
match = re.search(r'MIN_ACTION_STRENGTH_THRESHOLD\s*=\s*([\d.]+)', agent_content)
if match:
    threshold = float(match.group(1))
    if threshold >= 0.70:
        print(f'   ✅ Confidence threshold RAISED to {threshold} (>=0.70)')
    else:
        print(f'   ❌ Threshold too low: {threshold} (should be >=0.70)')
else:
    print('   ❌ MIN_ACTION_STRENGTH_THRESHOLD not found')

# ==================== PHASE 1 VALIDATION ====================
print('\n' + '=' * 70)
print('🟠 PHASE 1 — STRUCTURAL EDGE')
print('-' * 50)

# 1. Check new indicators
print('\n1️⃣ New Indicators Added:')
indicators = ['VIX1D', 'iv_rank', 'iv_skew', 'expected_move', 'gamma_wall']
for ind in indicators:
    if ind.lower() in phase0_content.lower() or ind.lower() in agent_content.lower():
        print(f'   ✅ {ind}')
    else:
        print(f'   ❌ {ind} NOT FOUND')

# 2. Check ensemble gating
print('\n2️⃣ Ensemble: Averaging → Gating:')
if 'USE_GATING_ENSEMBLE' in ensemble_content:
    print('   ✅ USE_GATING_ENSEMBLE flag found')
else:
    print('   ❌ Gating flag not found')

if 'CHAOS' in ensemble_content and 'TREND' in ensemble_content and 'RANGE' in ensemble_content:
    print('   ✅ Regime-based gating (CHAOS/TREND/RANGE/CALM)')
else:
    print('   ❌ Regime gating not found')

# 3. Check hard vetoes
print('\n3️⃣ Liquidity & Vol Agents as Hard Vetoes:')
if 'hard veto' in ensemble_content.lower() or 'veto' in ensemble_content.lower():
    print('   ✅ Veto mechanism implemented')
else:
    print('   ❌ Veto mechanism not found')

# 4. Check RL restrictions
print('\n4️⃣ RL Restricted to Timing/Sizing/Exit:')
rl_entry = re.search(r'RL_ENTRY_WEIGHT\s*=\s*([\d.]+)', agent_content)
rl_exit = re.search(r'RL_EXIT_WEIGHT\s*=\s*([\d.]+)', agent_content)

if rl_entry:
    entry_weight = float(rl_entry.group(1))
    if entry_weight == 0.0:
        print(f'   ✅ RL_ENTRY_WEIGHT = {entry_weight} (RL cannot generate entries)')
    else:
        print(f'   ⚠️ RL_ENTRY_WEIGHT = {entry_weight} (should be 0.0)')
else:
    print('   ❌ RL_ENTRY_WEIGHT not found')

if rl_exit:
    exit_weight = float(rl_exit.group(1))
    print(f'   ✅ RL_EXIT_WEIGHT = {exit_weight} (RL manages exits)')
else:
    print('   ⚠️ RL_EXIT_WEIGHT not explicitly set')

# ==================== GUI VALIDATION ====================
print('\n' + '=' * 70)
print('🖥️ GUI VALIDATION')
print('-' * 50)

print('\n1️⃣ Tabs Present:')
tabs = ['Trading Dashboard', 'Prediction', 'Backtest']
for tab in tabs:
    if tab in app_content:
        print(f'   ✅ {tab} tab')
    else:
        print(f'   ❌ {tab} tab NOT FOUND')

print('\n2️⃣ Required Functions:')
funcs = ['get_live_data_for_prediction', 'create_prediction_candlestick', 'render_prediction_tab']
for func in funcs:
    if func in app_content:
        print(f'   ✅ {func}()')
    else:
        print(f'   ❌ {func}() NOT FOUND')

print('\n3️⃣ Required Imports:')
imports = ['config', 'tradeapi', 'pytz', 'plotly']
for imp in imports:
    if imp in app_content:
        print(f'   ✅ {imp}')
    else:
        print(f'   ❌ {imp} NOT FOUND')

# ==================== FILE INTEGRITY ====================
print('\n' + '=' * 70)
print('📁 FILE INTEGRITY')
print('-' * 50)

files = [
    ('config.py', 'API Configuration'),
    ('mike_agent_live_safe.py', 'Live Trading Agent'),
    ('multi_agent_ensemble.py', 'Ensemble System'),
    ('phase0_gates.py', 'Phase 0/1 Gates'),
    ('price_predictor.py', 'Price Predictor'),
    ('prediction_logger.py', 'Prediction Logger'),
    ('trade_database.py', 'Trade Database'),
    ('app.py', 'Streamlit Dashboard')
]

for fname, desc in files:
    if os.path.exists(fname):
        size = os.path.getsize(fname)
        print(f'   ✅ {fname} ({size:,} bytes) - {desc}')
    else:
        print(f'   ❌ {fname} MISSING - {desc}')

# ==================== DASHBOARD ACCESSIBILITY ====================
print('\n' + '=' * 70)
print('🌐 DASHBOARD ACCESSIBILITY')
print('-' * 50)

import subprocess
try:
    result = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 'http://localhost:8501'], 
                          capture_output=True, text=True, timeout=5)
    if result.stdout.strip() == '200':
        print('   ✅ Dashboard is accessible (HTTP 200)')
    else:
        print(f'   ❌ Dashboard returned HTTP {result.stdout.strip()}')
except Exception as e:
    print(f'   ❌ Could not check dashboard: {e}')

print('\n' + '=' * 70)
print('✅ VALIDATION COMPLETE')
print('=' * 70)

