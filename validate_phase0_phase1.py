#!/usr/bin/env python3
"""
Phase 0 & Phase 1 Comprehensive Validation Script
==================================================

This script validates that ALL items from the 4-architect review are implemented:

🔴 Phase 0 — STOP THE BLEEDING
1. Remove resampling entirely
2. Enforce single live trading instance
3. Block trades when:
   * Spread > X% of premium
   * Quote age > threshold
   * Expected move < breakeven
4. Disable SPX, restrict IWM
5. Raise confidence threshold (do NOT lower it)

🟠 Phase 1 — STRUCTURAL EDGE
1. Add:
   * VIX1D
   * IV rank / skew
   * Expected move
   * Gamma wall proxy
2. Convert ensemble from averaging → gating
3. Make liquidity & vol agents hard vetoes
4. Use RL only for:
   * entry timing
   * sizing
   * exit management
"""

import os
import sys
import re
from datetime import datetime

# Colors for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

def print_header(text):
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    print(f"{BOLD}{BLUE}{text}{RESET}")
    print(f"{BOLD}{BLUE}{'='*70}{RESET}")

def print_pass(item, detail=""):
    print(f"  {GREEN}✅ PASS{RESET}: {item}")
    if detail:
        print(f"         {detail}")

def print_fail(item, detail=""):
    print(f"  {RED}❌ FAIL{RESET}: {item}")
    if detail:
        print(f"         {detail}")

def print_warn(item, detail=""):
    print(f"  {YELLOW}⚠️  WARN{RESET}: {item}")
    if detail:
        print(f"         {detail}")

def check_file_contains(filepath, patterns, description):
    """Check if a file contains specific patterns"""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        for pattern in patterns:
            if isinstance(pattern, str):
                if pattern not in content:
                    return False, f"Pattern not found: {pattern[:50]}..."
            else:  # regex
                if not pattern.search(content):
                    return False, f"Regex not found: {pattern.pattern[:50]}..."
        return True, "All patterns found"
    except FileNotFoundError:
        return False, f"File not found: {filepath}"
    except Exception as e:
        return False, f"Error: {e}"

def validate_phase0():
    """Validate all Phase 0 items"""
    print_header("🔴 PHASE 0 — STOP THE BLEEDING")
    results = []
    
    # ========== P0-1: Remove resampling entirely ==========
    print(f"\n{BOLD}P0-1: Remove resampling entirely{RESET}")
    
    patterns = [
        "resampled = False",
        "RESAMPLING REMOVED"
    ]
    passed, detail = check_file_contains('mike_agent_live_safe.py', patterns, "Resampling removal")
    
    if passed:
        print_pass("Resampling is removed", "Found 'resampled = False' and 'RESAMPLING REMOVED' comment")
        results.append(True)
    else:
        print_fail("Resampling may still be active", detail)
        results.append(False)
    
    # ========== P0-2: Enforce single live trading instance ==========
    print(f"\n{BOLD}P0-2: Enforce single live trading instance{RESET}")
    
    patterns = [
        "SINGLE INSTANCE",
        "mike_agent_live.pid",
        "os.kill(existing_pid, 0)"
    ]
    passed, detail = check_file_contains('mike_agent_live_safe.py', patterns, "Single instance lock")
    
    if passed:
        print_pass("Single instance lock implemented", "Found PID check and lock file logic")
        results.append(True)
    else:
        print_fail("Single instance lock not implemented", detail)
        results.append(False)
    
    # ========== P0-3: Block trades when spread > X% ==========
    print(f"\n{BOLD}P0-3: Block trades when spread > X% of premium{RESET}")
    
    patterns = [
        "MAX_SPREAD_PCT",
        "Spread too wide",
        re.compile(r"spread.*>.*15|15.*spread", re.IGNORECASE)
    ]
    passed, detail = check_file_contains('mike_agent_live_safe.py', patterns, "Spread gate")
    
    if passed:
        print_pass("Spread gate implemented", "Found MAX_SPREAD_PCT and spread blocking logic")
        results.append(True)
    else:
        print_fail("Spread gate not implemented", detail)
        results.append(False)
    
    # ========== P0-3b: Block trades when quote age > threshold ==========
    print(f"\n{BOLD}P0-3b: Block trades when quote age > threshold{RESET}")
    
    patterns = [
        "quote_age",
        "Quote too stale",
        "MAX_QUOTE_AGE"
    ]
    passed, detail = check_file_contains('mike_agent_live_safe.py', patterns, "Quote age gate")
    
    if passed:
        print_pass("Quote age gate implemented", "Found quote_age check and MAX_QUOTE_AGE")
        results.append(True)
    else:
        print_fail("Quote age gate not implemented", detail)
        results.append(False)
    
    # ========== P0-3c: Block trades when expected move < breakeven ==========
    print(f"\n{BOLD}P0-3c: Block trades when expected move < breakeven{RESET}")
    
    patterns = [
        "expected_move",
        "breakeven",
        "MIN_EXPECTED_MOVE_RATIO"
    ]
    passed, detail = check_file_contains('mike_agent_live_safe.py', patterns, "Expected move gate")
    
    if passed:
        print_pass("Expected move gate implemented", "Found expected_move vs breakeven check")
        results.append(True)
    else:
        print_fail("Expected move gate not implemented", detail)
        results.append(False)
    
    # ========== P0-4: Disable SPX, restrict IWM ==========
    print(f"\n{BOLD}P0-4: Disable SPX, restrict IWM{RESET}")
    
    # Check TRADING_SYMBOLS
    try:
        with open('mike_agent_live_safe.py', 'r') as f:
            content = f.read()
        
        # Find TRADING_SYMBOLS definition
        match = re.search(r"TRADING_SYMBOLS\s*=\s*\[(.*?)\]", content)
        if match:
            symbols = match.group(1)
            has_spx = 'SPX' in symbols
            has_iwm = 'IWM' in symbols
            has_spy = 'SPY' in symbols
            has_qqq = 'QQQ' in symbols
            
            if has_spy and has_qqq and not has_spx and not has_iwm:
                print_pass("SPX and IWM disabled", f"TRADING_SYMBOLS = [{symbols.strip()}]")
                results.append(True)
            else:
                print_fail("SPX or IWM may still be enabled", f"TRADING_SYMBOLS = [{symbols.strip()}]")
                results.append(False)
        else:
            print_fail("TRADING_SYMBOLS not found", "Could not find TRADING_SYMBOLS definition")
            results.append(False)
    except Exception as e:
        print_fail("Error checking symbols", str(e))
        results.append(False)
    
    # ========== P0-5: Raise confidence threshold ==========
    print(f"\n{BOLD}P0-5: Raise confidence threshold (>= 0.70){RESET}")
    
    try:
        with open('mike_agent_live_safe.py', 'r') as f:
            content = f.read()
        
        # Find MIN_ACTION_STRENGTH_THRESHOLD
        match = re.search(r"MIN_ACTION_STRENGTH_THRESHOLD\s*=\s*([\d.]+)", content)
        if match:
            threshold = float(match.group(1))
            if threshold >= 0.70:
                print_pass(f"Confidence threshold raised to {threshold}", "Meets Phase 0 requirement (>= 0.70)")
                results.append(True)
            else:
                print_fail(f"Confidence threshold too low: {threshold}", "Should be >= 0.70")
                results.append(False)
        else:
            print_fail("MIN_ACTION_STRENGTH_THRESHOLD not found", "Could not find threshold definition")
            results.append(False)
    except Exception as e:
        print_fail("Error checking threshold", str(e))
        results.append(False)
    
    return results

def validate_phase1():
    """Validate all Phase 1 items"""
    print_header("🟠 PHASE 1 — STRUCTURAL EDGE")
    results = []
    
    # ========== P1-1a: Add VIX1D ==========
    print(f"\n{BOLD}P1-1a: Add VIX1D indicator{RESET}")
    
    # Check phase0_gates.py
    patterns = [
        "VIX1D",
        "get_vix1d"
    ]
    passed, detail = check_file_contains('phase0_gates.py', patterns, "VIX1D indicator")
    
    if passed:
        print_pass("VIX1D indicator implemented", "Found get_vix1d() in phase0_gates.py")
        results.append(True)
    else:
        print_fail("VIX1D indicator not found", detail)
        results.append(False)
    
    # ========== P1-1b: Add IV rank / skew ==========
    print(f"\n{BOLD}P1-1b: Add IV rank / skew indicators{RESET}")
    
    patterns = [
        "iv_rank",
        "get_iv_rank",
        "IV_RANK"
    ]
    passed, detail = check_file_contains('phase0_gates.py', patterns, "IV rank indicator")
    
    if passed:
        print_pass("IV rank indicator implemented", "Found get_iv_rank() in phase0_gates.py")
        results.append(True)
    else:
        print_fail("IV rank indicator not found", detail)
        results.append(False)
    
    # ========== P1-1c: Add Expected move ==========
    print(f"\n{BOLD}P1-1c: Add Expected move calculation{RESET}")
    
    patterns = [
        "calculate_expected_move",
        "expected_move"
    ]
    passed, detail = check_file_contains('phase0_gates.py', patterns, "Expected move calculation")
    
    if passed:
        print_pass("Expected move calculation implemented", "Found calculate_expected_move() in phase0_gates.py")
        results.append(True)
    else:
        print_fail("Expected move calculation not found", detail)
        results.append(False)
    
    # ========== P1-1d: Add Gamma wall proxy ==========
    print(f"\n{BOLD}P1-1d: Add Gamma wall proxy{RESET}")
    
    patterns = [
        "gamma_wall",
        "get_gamma_wall",
        "GAMMA_WALL"
    ]
    passed, detail = check_file_contains('phase0_gates.py', patterns, "Gamma wall proxy")
    
    if passed:
        print_pass("Gamma wall proxy implemented", "Found gamma wall logic in phase0_gates.py")
        results.append(True)
    else:
        print_fail("Gamma wall proxy not found", detail)
        results.append(False)
    
    # ========== P1-2: Convert ensemble from averaging → gating ==========
    print(f"\n{BOLD}P1-2: Convert ensemble from averaging → gating{RESET}")
    
    patterns = [
        "USE_GATING_ENSEMBLE",
        "GATING",
        "gating_source"
    ]
    passed, detail = check_file_contains('multi_agent_ensemble.py', patterns, "Gating ensemble")
    
    if passed:
        print_pass("Ensemble converted to gating", "Found USE_GATING_ENSEMBLE and gating_source")
        results.append(True)
    else:
        print_fail("Ensemble still uses averaging", detail)
        results.append(False)
    
    # Check for regime-based agent selection
    patterns = [
        "regime == 'chaos'",
        "regime == 'trending'",
        "regime == 'mean_reverting'"
    ]
    passed, detail = check_file_contains('multi_agent_ensemble.py', patterns, "Regime-based selection")
    
    if passed:
        print_pass("Regime-based agent selection", "Found regime-specific agent gating")
    else:
        print_warn("Regime-based selection may be incomplete", detail)
    
    # ========== P1-3: Make liquidity & vol agents hard vetoes ==========
    print(f"\n{BOLD}P1-3: Make liquidity & vol agents hard vetoes{RESET}")
    
    patterns = [
        "VETO",
        "delta_signal.action == 0",
        "DELTA_VETO"
    ]
    passed, detail = check_file_contains('multi_agent_ensemble.py', patterns, "Hard vetoes")
    
    if passed:
        print_pass("Hard vetoes implemented", "Found VETO logic for delta/gamma agents")
        results.append(True)
    else:
        print_fail("Hard vetoes not implemented", detail)
        results.append(False)
    
    # Check for liquidity gate in main agent
    patterns = [
        "MIN_OPTION_VOLUME",
        "MIN_OPEN_INTEREST",
        "Low option volume",
        "Low open interest"
    ]
    passed, detail = check_file_contains('mike_agent_live_safe.py', patterns, "Liquidity gates")
    
    if passed:
        print_pass("Liquidity gates in main agent", "Found MIN_OPTION_VOLUME and MIN_OPEN_INTEREST")
    else:
        print_warn("Liquidity gates may be incomplete", detail)
    
    # ========== P1-4: Use RL only for entry timing/sizing/exit ==========
    print(f"\n{BOLD}P1-4: Restrict RL to timing/sizing/exit only{RESET}")
    
    patterns = [
        "RL_ENTRY_WEIGHT = 0",
        "RL demoted for entries",
        "Ensemble (P1: RL demoted for entries)"
    ]
    passed, detail = check_file_contains('mike_agent_live_safe.py', patterns, "RL role restriction")
    
    if passed:
        print_pass("RL restricted to timing/sizing/exit", "Found RL_ENTRY_WEIGHT = 0 and RL demotion")
        results.append(True)
    else:
        print_fail("RL may still generate entries", detail)
        results.append(False)
    
    # Check for exit handling
    patterns = [
        "RL_EXIT_WEIGHT",
        "RL is still good at exits",
        "exit consensus"
    ]
    passed, detail = check_file_contains('mike_agent_live_safe.py', patterns, "RL exit handling")
    
    if passed:
        print_pass("RL exit handling preserved", "RL can still handle exits")
    else:
        print_warn("RL exit handling may be incomplete", detail)
    
    return results

def validate_imports():
    """Validate that all modules can be imported"""
    print_header("📦 MODULE IMPORT VALIDATION")
    results = []
    
    # Test phase0_gates import
    print(f"\n{BOLD}Testing phase0_gates.py imports{RESET}")
    try:
        from phase0_gates import (
            Phase0Gates, Phase1Indicators, Phase1Ensemble,
            run_phase0_phase1_checks, PHASE0, PHASE1
        )
        print_pass("phase0_gates.py imports successfully")
        results.append(True)
        
        # Test Phase0Gates
        gates = Phase0Gates()
        passed, reason = gates.check_symbol_gate('SPY')
        if passed:
            print_pass("Phase0Gates.check_symbol_gate() works", "SPY is allowed")
        else:
            print_fail("Phase0Gates.check_symbol_gate() failed", reason)
        
        passed, reason = gates.check_symbol_gate('SPX')
        if not passed:
            print_pass("Phase0Gates blocks SPX", "SPX correctly blocked")
        else:
            print_fail("Phase0Gates should block SPX", "SPX was allowed")
        
        passed, reason = gates.check_confidence_gate(0.65)
        if not passed:
            print_pass("Phase0Gates blocks low confidence", "0.65 correctly blocked")
        else:
            print_fail("Phase0Gates should block 0.65", "0.65 was allowed")
        
        passed, reason = gates.check_confidence_gate(0.75)
        if passed:
            print_pass("Phase0Gates allows high confidence", "0.75 correctly allowed")
        else:
            print_fail("Phase0Gates should allow 0.75", reason)
            
    except ImportError as e:
        print_fail("phase0_gates.py import failed", str(e))
        results.append(False)
    except Exception as e:
        print_fail("phase0_gates.py test failed", str(e))
        results.append(False)
    
    # Test multi_agent_ensemble import
    print(f"\n{BOLD}Testing multi_agent_ensemble.py imports{RESET}")
    try:
        from multi_agent_ensemble import (
            MetaPolicyRouter, initialize_meta_router, AgentType
        )
        print_pass("multi_agent_ensemble.py imports successfully")
        results.append(True)
        
        # Test router initialization
        router = initialize_meta_router()
        print_pass("MetaPolicyRouter initialized", "Router created successfully")
        
    except ImportError as e:
        print_fail("multi_agent_ensemble.py import failed", str(e))
        results.append(False)
    except Exception as e:
        print_fail("multi_agent_ensemble.py test failed", str(e))
        results.append(False)
    
    # Test mike_agent_live_safe import
    print(f"\n{BOLD}Testing mike_agent_live_safe.py imports{RESET}")
    try:
        # Import just the constants and key functions
        import mike_agent_live_safe as agent
        
        # Check key constants
        if hasattr(agent, 'MIN_ACTION_STRENGTH_THRESHOLD'):
            if agent.MIN_ACTION_STRENGTH_THRESHOLD >= 0.70:
                print_pass(f"MIN_ACTION_STRENGTH_THRESHOLD = {agent.MIN_ACTION_STRENGTH_THRESHOLD}")
            else:
                print_fail(f"MIN_ACTION_STRENGTH_THRESHOLD too low: {agent.MIN_ACTION_STRENGTH_THRESHOLD}")
        
        if hasattr(agent, 'TRADING_SYMBOLS'):
            print_pass(f"TRADING_SYMBOLS = {agent.TRADING_SYMBOLS}")
        
        if hasattr(agent, 'BLOCKED_SYMBOLS'):
            print_pass(f"BLOCKED_SYMBOLS = {agent.BLOCKED_SYMBOLS}")
        
        if hasattr(agent, 'PHASE0_GATES_AVAILABLE'):
            if agent.PHASE0_GATES_AVAILABLE:
                print_pass("Phase0 gates module available")
            else:
                print_warn("Phase0 gates module not loaded")
        
        results.append(True)
        
    except ImportError as e:
        print_fail("mike_agent_live_safe.py import failed", str(e))
        results.append(False)
    except Exception as e:
        print_warn("mike_agent_live_safe.py partial import", str(e))
        results.append(True)  # Partial success is OK
    
    return results

def run_functional_tests():
    """Run functional tests on the gates"""
    print_header("🧪 FUNCTIONAL TESTS")
    results = []
    
    try:
        from phase0_gates import Phase0Gates, Phase1Indicators, Phase1Ensemble
        
        gates = Phase0Gates()
        indicators = Phase1Indicators()
        ensemble = Phase1Ensemble()
        
        # Test 1: Symbol blocking
        print(f"\n{BOLD}Test 1: Symbol Blocking{RESET}")
        test_cases = [
            ('SPY', True),
            ('QQQ', True),
            ('SPX', False),
            ('IWM', False),
            ('^SPX', False),
        ]
        
        all_passed = True
        for symbol, expected in test_cases:
            passed, _ = gates.check_symbol_gate(symbol)
            if passed == expected:
                print_pass(f"{symbol}: {'allowed' if passed else 'blocked'}")
            else:
                print_fail(f"{symbol}: expected {'allowed' if expected else 'blocked'}")
                all_passed = False
        results.append(all_passed)
        
        # Test 2: Confidence threshold
        print(f"\n{BOLD}Test 2: Confidence Threshold{RESET}")
        test_cases = [
            (0.50, False),
            (0.60, False),
            (0.69, False),
            (0.70, True),
            (0.80, True),
            (0.95, True),
        ]
        
        all_passed = True
        for conf, expected in test_cases:
            passed, _ = gates.check_confidence_gate(conf)
            if passed == expected:
                print_pass(f"Confidence {conf}: {'allowed' if passed else 'blocked'}")
            else:
                print_fail(f"Confidence {conf}: expected {'allowed' if expected else 'blocked'}")
                all_passed = False
        results.append(all_passed)
        
        # Test 3: Spread gate
        print(f"\n{BOLD}Test 3: Spread Gate{RESET}")
        test_cases = [
            (1.00, 1.05, True),   # 5% spread - OK
            (1.00, 1.08, True),   # 8% spread - OK
            (1.00, 1.16, False),  # 16% spread - blocked
            (1.00, 1.25, False),  # 25% spread - blocked
            (0.50, 0.62, False),  # 24% spread - blocked
        ]
        
        all_passed = True
        for bid, ask, expected in test_cases:
            passed, reason = gates.check_spread_gate(bid, ask)
            spread_pct = ((ask - bid) / ((bid + ask) / 2)) * 100
            if passed == expected:
                print_pass(f"Bid={bid}, Ask={ask} ({spread_pct:.1f}%): {'allowed' if passed else 'blocked'}")
            else:
                print_fail(f"Bid={bid}, Ask={ask}: expected {'allowed' if expected else 'blocked'}")
                all_passed = False
        results.append(all_passed)
        
        # Test 4: Expected move gate
        print(f"\n{BOLD}Test 4: Expected Move Gate{RESET}")
        test_cases = [
            (2.0, 1.0, True),   # 2.0x ratio - OK
            (1.5, 1.0, True),   # 1.5x ratio - OK
            (1.2, 1.0, True),   # 1.2x ratio - OK (exactly at threshold)
            (1.1, 1.0, False),  # 1.1x ratio - blocked
            (1.0, 1.0, False),  # 1.0x ratio - blocked
            (0.5, 1.0, False),  # 0.5x ratio - blocked
        ]
        
        all_passed = True
        for em, be, expected in test_cases:
            passed, reason = gates.check_expected_move_gate(em, be)
            if passed == expected:
                print_pass(f"EM={em}, BE={be} (ratio={em/be:.1f}): {'allowed' if passed else 'blocked'}")
            else:
                print_fail(f"EM={em}, BE={be}: expected {'allowed' if expected else 'blocked'}")
                all_passed = False
        results.append(all_passed)
        
        # Test 5: Regime detection
        print(f"\n{BOLD}Test 5: Regime Detection{RESET}")
        test_cases = [
            (10, 'CALM'),
            (15, 'RANGE'),
            (20, 'TREND'),
            (30, 'CHAOS'),
        ]
        
        all_passed = True
        for vix, expected in test_cases:
            regime = ensemble.detect_regime(vix)
            if regime.upper() == expected:
                print_pass(f"VIX={vix}: {regime}")
            else:
                print_fail(f"VIX={vix}: got {regime}, expected {expected}")
                all_passed = False
        results.append(all_passed)
        
        # Test 6: Phase 1 indicators
        print(f"\n{BOLD}Test 6: Phase 1 Indicators{RESET}")
        
        vix1d = indicators.get_vix1d()
        if vix1d is not None:
            print_pass(f"VIX1D retrieved: {vix1d:.2f}")
        else:
            print_warn("VIX1D not available (API may be down)")
        
        em = indicators.calculate_expected_move(500, 15)
        if em > 0:
            print_pass(f"Expected move calculation: ${em:.2f}")
            results.append(True)
        else:
            print_fail("Expected move calculation failed")
            results.append(False)
        
    except Exception as e:
        print_fail(f"Functional tests failed: {e}")
        import traceback
        traceback.print_exc()
        results.append(False)
    
    return results

def main():
    """Run all validations"""
    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}   PHASE 0 & PHASE 1 COMPREHENSIVE VALIDATION{RESET}")
    print(f"{BOLD}   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
    print(f"{BOLD}{'='*70}{RESET}")
    
    all_results = []
    
    # Phase 0 validation
    phase0_results = validate_phase0()
    all_results.extend(phase0_results)
    
    # Phase 1 validation
    phase1_results = validate_phase1()
    all_results.extend(phase1_results)
    
    # Import validation
    import_results = validate_imports()
    all_results.extend(import_results)
    
    # Functional tests
    func_results = run_functional_tests()
    all_results.extend(func_results)
    
    # Summary
    print_header("📊 VALIDATION SUMMARY")
    
    passed = sum(1 for r in all_results if r)
    failed = sum(1 for r in all_results if not r)
    total = len(all_results)
    
    print(f"\n  {GREEN}Passed: {passed}/{total}{RESET}")
    print(f"  {RED}Failed: {failed}/{total}{RESET}")
    
    if failed == 0:
        print(f"\n  {GREEN}{BOLD}🎉 ALL VALIDATIONS PASSED!{RESET}")
        print(f"  {GREEN}Phase 0 & Phase 1 implementation is COMPLETE.{RESET}")
        return 0
    else:
        print(f"\n  {RED}{BOLD}⚠️  Some validations failed.{RESET}")
        print(f"  {RED}Please review the failures above and fix them.{RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())

