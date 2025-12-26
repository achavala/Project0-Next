"""
Phase 0 & Phase 1 Gates for 0-DTE Options Trading
=================================================

Based on 4-architect review feedback:
- Phase 0: STOP THE BLEEDING (hard gates, no ML changes)
- Phase 1: STRUCTURAL EDGE (new indicators, ensemble gating)

Key insight: "You are optimizing directional correctness in a market 
where directional correctness is secondary."

In 0-DTE:
- What matters: Gamma/vanna flows, IV term structure, liquidity, expected move
- What we were doing: RSI, MACD, EMA (lagging duplicates of price)
"""

import os
import logging
from typing import Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import pytz

# Try to import data sources
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# ============================================================================
# PHASE 0 CONFIGURATION - STOP THE BLEEDING
# ============================================================================

@dataclass
class Phase0Config:
    """Phase 0 hard gates configuration"""
    
    # 1. Confidence threshold (RAISED from 0.60)
    MIN_CONFIDENCE_THRESHOLD: float = 0.70  # Raised from 0.60
    
    # 2. Spread gate: Block if spread > X% of premium
    MAX_SPREAD_PCT_OF_PREMIUM: float = 0.15  # 15% max spread
    
    # 3. Quote age gate: Block if quote is stale
    MAX_QUOTE_AGE_SECONDS: int = 5  # 5 seconds max
    
    # 4. Expected move gate: Block if expected_move < breakeven
    REQUIRE_EXPECTED_MOVE_EDGE: bool = True
    MIN_EXPECTED_MOVE_RATIO: float = 1.2  # Expected move must be 1.2x breakeven
    
    # 5. Symbol restrictions
    ALLOWED_SYMBOLS: tuple = ('SPY', 'QQQ')  # Disabled SPX, IWM
    BLOCKED_SYMBOLS: tuple = ('SPX', 'IWM', '^SPX')  # Explicitly blocked
    
    # 6. Single instance enforcement
    ENFORCE_SINGLE_INSTANCE: bool = True
    INSTANCE_LOCK_FILE: str = '/tmp/mike_agent_0dte.lock'
    
    # 7. Liquidity gates
    MIN_OPTION_VOLUME: int = 100  # Minimum daily volume
    MIN_OPEN_INTEREST: int = 500  # Minimum OI
    MAX_BID_ASK_SPREAD: float = 0.10  # $0.10 max absolute spread


# ============================================================================
# PHASE 1 CONFIGURATION - STRUCTURAL EDGE
# ============================================================================

@dataclass
class Phase1Config:
    """Phase 1 structural edge configuration"""
    
    # 1. VIX1D (1-day VIX) - critical for 0-DTE
    USE_VIX1D: bool = True
    VIX1D_SYMBOL: str = 'VIX1D.X'  # Cboe 1-day VIX
    VIX1D_THRESHOLD_LOW: float = 12.0  # Below = calm
    VIX1D_THRESHOLD_HIGH: float = 20.0  # Above = elevated
    
    # 2. IV Rank / Skew
    USE_IV_RANK: bool = True
    IV_RANK_LOW: float = 20.0  # Percentile
    IV_RANK_HIGH: float = 80.0  # Percentile
    
    # 3. Expected Move calculation
    EXPECTED_MOVE_PERIODS: int = 20  # Lookback for realized vol
    
    # 4. Gamma wall proxy
    USE_GAMMA_WALLS: bool = True
    GAMMA_WALL_DISTANCE_PCT: float = 0.005  # 0.5% from gamma wall = caution
    
    # 5. Ensemble gating (not averaging)
    ENSEMBLE_MODE: str = 'GATING'  # 'GATING' or 'AVERAGING'
    
    # 6. Hard vetoes
    LIQUIDITY_VETO_ENABLED: bool = True
    VOLATILITY_VETO_ENABLED: bool = True
    
    # 7. RL role restrictions
    RL_ALLOWED_FUNCTIONS: tuple = ('TIMING', 'SIZING', 'EXIT')  # Not entry signals


# Global configs
PHASE0 = Phase0Config()
PHASE1 = Phase1Config()


# ============================================================================
# PHASE 0 GATES - HARD BLOCKS
# ============================================================================

class Phase0Gates:
    """
    Phase 0: Hard gates that block trades unconditionally.
    These run BEFORE any ML/RL logic.
    """
    
    def __init__(self, config: Phase0Config = PHASE0):
        self.config = config
        self.logger = logging.getLogger('Phase0Gates')
        self._instance_acquired = False
        
    def check_all_gates(
        self,
        symbol: str,
        confidence: float,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        quote_time: Optional[datetime] = None,
        expected_move: Optional[float] = None,
        breakeven_move: Optional[float] = None,
        option_volume: Optional[int] = None,
        open_interest: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Run all Phase 0 gates.
        
        Returns:
            (passed, reason): True if all gates pass, else (False, block_reason)
        """
        
        # Gate 1: Symbol allowed?
        passed, reason = self.check_symbol_gate(symbol)
        if not passed:
            return False, reason
            
        # Gate 2: Confidence threshold
        passed, reason = self.check_confidence_gate(confidence)
        if not passed:
            return False, reason
            
        # Gate 3: Spread check
        if bid is not None and ask is not None:
            passed, reason = self.check_spread_gate(bid, ask)
            if not passed:
                return False, reason
                
        # Gate 4: Quote age
        if quote_time is not None:
            passed, reason = self.check_quote_age_gate(quote_time)
            if not passed:
                return False, reason
                
        # Gate 5: Expected move vs breakeven
        if expected_move is not None and breakeven_move is not None:
            passed, reason = self.check_expected_move_gate(expected_move, breakeven_move)
            if not passed:
                return False, reason
                
        # Gate 6: Liquidity
        if option_volume is not None:
            passed, reason = self.check_liquidity_gate(option_volume, open_interest)
            if not passed:
                return False, reason
        
        return True, "All Phase 0 gates passed"
    
    def check_symbol_gate(self, symbol: str) -> Tuple[bool, str]:
        """Block disallowed symbols (SPX, IWM)"""
        if symbol in self.config.BLOCKED_SYMBOLS:
            return False, f"❌ P0-BLOCK: {symbol} is disabled (SPX/IWM blocked per architect review)"
        if symbol not in self.config.ALLOWED_SYMBOLS:
            return False, f"❌ P0-BLOCK: {symbol} not in allowed list {self.config.ALLOWED_SYMBOLS}"
        return True, "Symbol allowed"
    
    def check_confidence_gate(self, confidence: float) -> Tuple[bool, str]:
        """Block low confidence trades (threshold raised to 0.70)"""
        if confidence < self.config.MIN_CONFIDENCE_THRESHOLD:
            return False, f"❌ P0-BLOCK: Confidence {confidence:.3f} < {self.config.MIN_CONFIDENCE_THRESHOLD:.3f} (raised threshold)"
        return True, "Confidence OK"
    
    def check_spread_gate(self, bid: float, ask: float) -> Tuple[bool, str]:
        """Block if spread > X% of premium"""
        if bid <= 0:
            return False, "❌ P0-BLOCK: Invalid bid price (<=0)"
        
        spread = ask - bid
        mid_price = (bid + ask) / 2
        spread_pct = spread / mid_price if mid_price > 0 else 1.0
        
        if spread_pct > self.config.MAX_SPREAD_PCT_OF_PREMIUM:
            return False, f"❌ P0-BLOCK: Spread {spread_pct:.1%} > {self.config.MAX_SPREAD_PCT_OF_PREMIUM:.1%} of premium"
        
        if spread > self.config.MAX_BID_ASK_SPREAD:
            return False, f"❌ P0-BLOCK: Spread ${spread:.2f} > ${self.config.MAX_BID_ASK_SPREAD:.2f} max"
            
        return True, f"Spread OK ({spread_pct:.1%})"
    
    def check_quote_age_gate(self, quote_time: datetime) -> Tuple[bool, str]:
        """Block if quote is stale"""
        now = datetime.now(pytz.UTC)
        
        # Ensure quote_time is timezone-aware
        if quote_time.tzinfo is None:
            quote_time = pytz.UTC.localize(quote_time)
        
        age_seconds = (now - quote_time).total_seconds()
        
        if age_seconds > self.config.MAX_QUOTE_AGE_SECONDS:
            return False, f"❌ P0-BLOCK: Quote age {age_seconds:.1f}s > {self.config.MAX_QUOTE_AGE_SECONDS}s max"
        
        return True, f"Quote fresh ({age_seconds:.1f}s)"
    
    def check_expected_move_gate(self, expected_move: float, breakeven_move: float) -> Tuple[bool, str]:
        """
        Block if expected_move < breakeven_move.
        
        This is THE critical gate per architect feedback:
        "This single rule would eliminate most losses"
        """
        if not self.config.REQUIRE_EXPECTED_MOVE_EDGE:
            return True, "Expected move gate disabled"
        
        if breakeven_move <= 0:
            return False, "❌ P0-BLOCK: Invalid breakeven_move (<=0)"
        
        ratio = expected_move / breakeven_move
        
        if ratio < self.config.MIN_EXPECTED_MOVE_RATIO:
            return False, (
                f"❌ P0-BLOCK: Expected move ${expected_move:.2f} < {self.config.MIN_EXPECTED_MOVE_RATIO:.1f}x "
                f"breakeven ${breakeven_move:.2f} (ratio={ratio:.2f})"
            )
        
        return True, f"Expected move edge OK (ratio={ratio:.2f})"
    
    def check_liquidity_gate(
        self, 
        option_volume: int, 
        open_interest: Optional[int] = None
    ) -> Tuple[bool, str]:
        """Block illiquid options"""
        if option_volume < self.config.MIN_OPTION_VOLUME:
            return False, f"❌ P0-BLOCK: Volume {option_volume} < {self.config.MIN_OPTION_VOLUME} min"
        
        if open_interest is not None and open_interest < self.config.MIN_OPEN_INTEREST:
            return False, f"❌ P0-BLOCK: OI {open_interest} < {self.config.MIN_OPEN_INTEREST} min"
        
        return True, f"Liquidity OK (vol={option_volume})"
    
    def acquire_instance_lock(self) -> bool:
        """Enforce single trading instance"""
        if not self.config.ENFORCE_SINGLE_INSTANCE:
            return True
            
        lock_file = self.config.INSTANCE_LOCK_FILE
        
        # Check if lock exists and is recent
        if os.path.exists(lock_file):
            try:
                with open(lock_file, 'r') as f:
                    pid = int(f.read().strip())
                # Check if process is still running
                try:
                    os.kill(pid, 0)  # Signal 0 = check if exists
                    # Process exists - another instance running
                    self.logger.error(f"❌ Another instance (PID {pid}) is already running!")
                    return False
                except OSError:
                    # Process doesn't exist - stale lock
                    pass
            except:
                pass
        
        # Create lock file
        try:
            with open(lock_file, 'w') as f:
                f.write(str(os.getpid()))
            self._instance_acquired = True
            return True
        except Exception as e:
            self.logger.error(f"Failed to create lock file: {e}")
            return False
    
    def release_instance_lock(self):
        """Release the instance lock"""
        if self._instance_acquired and os.path.exists(self.config.INSTANCE_LOCK_FILE):
            try:
                os.remove(self.config.INSTANCE_LOCK_FILE)
                self._instance_acquired = False
            except:
                pass


# ============================================================================
# PHASE 1 INDICATORS - STRUCTURAL EDGE
# ============================================================================

class Phase1Indicators:
    """
    Phase 1: New indicators for structural edge.
    
    What was missing (per architect review):
    1. VIX1D (1-day VIX, not 30-day VIX)
    2. IV rank / skew
    3. Expected move calculation
    4. Gamma wall proxy
    """
    
    def __init__(self, config: Phase1Config = PHASE1):
        self.config = config
        self.logger = logging.getLogger('Phase1Indicators')
        self._vix1d_cache = {}
        self._iv_cache = {}
        
    def get_vix1d(self) -> Optional[float]:
        """
        Get VIX1D (1-day VIX).
        
        This is CRITICAL for 0-DTE because:
        - VIX (30-day) is useless for 30-minute options
        - VIX1D captures actual intraday volatility expectations
        """
        if not self.config.USE_VIX1D:
            return None
            
        # Try to get from Polygon/Massive API first
        try:
            import config as app_config
            api_key = getattr(app_config, 'MASSIVE_API_KEY', None) or os.getenv('MASSIVE_API_KEY')
            
            if api_key and REQUESTS_AVAILABLE:
                # Cboe VIX1D index
                url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/indices/tickers/I:VIX1D?apiKey={api_key}"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if 'ticker' in data and 'value' in data['ticker']:
                        return float(data['ticker']['value'])
        except Exception as e:
            self.logger.debug(f"VIX1D from Polygon failed: {e}")
        
        # Fallback: Estimate from VIX
        try:
            if YFINANCE_AVAILABLE:
                vix = yf.Ticker('^VIX')
                hist = vix.history(period='1d')
                if len(hist) > 0:
                    vix_30d = hist['Close'].iloc[-1]
                    # Rough approximation: VIX1D ≈ VIX * sqrt(1/30) * sqrt(30)
                    # Actually just use VIX as proxy with warning
                    self.logger.warning("Using VIX (30-day) as VIX1D proxy - less accurate for 0-DTE")
                    return vix_30d
        except Exception as e:
            self.logger.debug(f"VIX fallback failed: {e}")
        
        return None
    
    def get_iv_rank(self, symbol: str, lookback_days: int = 252) -> Optional[float]:
        """
        Calculate IV Rank (percentile of current IV vs historical).
        
        IV Rank = (Current IV - 52w Low) / (52w High - 52w Low) * 100
        """
        if not self.config.USE_IV_RANK:
            return None
            
        try:
            if YFINANCE_AVAILABLE:
                # Get historical data
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='1y')
                
                if len(hist) < 20:
                    return None
                
                # Calculate historical volatility as IV proxy
                returns = hist['Close'].pct_change().dropna()
                
                # Rolling 20-day realized vol (annualized)
                rolling_vol = returns.rolling(20).std() * (252 ** 0.5) * 100
                rolling_vol = rolling_vol.dropna()
                
                if len(rolling_vol) < 50:
                    return None
                
                current_vol = rolling_vol.iloc[-1]
                vol_min = rolling_vol.min()
                vol_max = rolling_vol.max()
                
                if vol_max - vol_min < 0.01:
                    return 50.0  # No range
                
                iv_rank = (current_vol - vol_min) / (vol_max - vol_min) * 100
                return float(iv_rank)
                
        except Exception as e:
            self.logger.debug(f"IV Rank calculation failed: {e}")
        
        return None
    
    def get_iv_skew(self, symbol: str) -> Optional[float]:
        """
        Calculate IV Skew (Put IV - Call IV).
        
        Positive skew = puts more expensive (fear)
        Negative skew = calls more expensive (greed)
        """
        # This requires options chain data - simplified for now
        # Full implementation would use options chain from Polygon
        return None
    
    def calculate_expected_move(
        self, 
        price: float, 
        iv: Optional[float] = None,
        time_to_expiry_hours: float = 6.5  # Full trading day
    ) -> float:
        """
        Calculate expected move for 0-DTE.
        
        Expected Move = Price * IV * sqrt(T/365)
        
        For 0-DTE with ~6.5 hours left:
        T = 6.5 / (24 * 365) ≈ 0.00074
        """
        if iv is None:
            # Use VIX1D or default
            iv = self.get_vix1d() or 15.0  # Default 15% if unavailable
        
        # Convert IV from percentage to decimal
        iv_decimal = iv / 100.0
        
        # Time in years
        T = time_to_expiry_hours / (24 * 365)
        
        # Expected move (1 standard deviation)
        expected_move = price * iv_decimal * (T ** 0.5)
        
        return expected_move
    
    def calculate_breakeven_move(
        self,
        premium: float,
        contracts: int = 1
    ) -> float:
        """
        Calculate breakeven move needed.
        
        For options: underlying must move by at least the premium paid
        (simplified - ignores Greeks)
        """
        # Cost basis
        total_cost = premium * contracts * 100  # 100 shares per contract
        
        # Per-share breakeven
        breakeven_per_share = premium
        
        return breakeven_per_share
    
    def get_gamma_wall_levels(self, symbol: str) -> Optional[Dict[str, float]]:
        """
        Estimate gamma wall levels.
        
        Gamma walls are strike prices with high gamma exposure.
        When price approaches, dealers must hedge aggressively.
        
        This is a simplified proxy - full implementation requires:
        - Options chain OI by strike
        - Gamma calculation per strike
        - Net dealer positioning
        """
        if not self.config.USE_GAMMA_WALLS:
            return None
        
        # Placeholder - would need options chain data
        # Return None to indicate data not available
        return None


# ============================================================================
# PHASE 1 ENSEMBLE - GATING (NOT AVERAGING)
# ============================================================================

class Phase1Ensemble:
    """
    Phase 1: Ensemble with GATING, not averaging.
    
    Problem with averaging:
    - Trend agent: 0.8 BUY
    - Mean reversion agent: 0.2 SELL
    - Average: 0.5 DO NOTHING
    - Result: Miss both breakouts AND ranges
    
    Solution (gating):
    - Detect regime first
    - Select appropriate agent
    - Ignore conflicting agents
    """
    
    def __init__(self, config: Phase1Config = PHASE1):
        self.config = config
        self.logger = logging.getLogger('Phase1Ensemble')
        
    def detect_regime(
        self,
        vix: float,
        vix1d: Optional[float] = None,
        iv_rank: Optional[float] = None,
        price_momentum: Optional[float] = None,
        volatility_ratio: Optional[float] = None
    ) -> str:
        """
        Detect current market regime.
        
        Regimes:
        - TREND: Strong directional movement
        - RANGE: Mean-reverting, bounded
        - CHAOS: High vol, no clear direction
        - CALM: Low vol, minimal movement
        """
        # Use VIX1D if available, else VIX
        effective_vix = vix1d if vix1d is not None else vix
        
        # IV Rank thresholds
        iv_low = iv_rank is not None and iv_rank < self.config.IV_RANK_LOW
        iv_high = iv_rank is not None and iv_rank > self.config.IV_RANK_HIGH
        
        # Regime detection logic
        if effective_vix > 25:
            return 'CHAOS'
        elif effective_vix > 18:
            if iv_high:
                return 'CHAOS'
            else:
                return 'TREND'
        elif effective_vix < 12:
            return 'CALM'
        else:
            # Medium VIX - check momentum
            if price_momentum is not None:
                if abs(price_momentum) > 0.5:  # Strong momentum
                    return 'TREND'
                else:
                    return 'RANGE'
            return 'RANGE'
    
    def gate_ensemble(
        self,
        regime: str,
        trend_signal: Tuple[int, float],  # (action, confidence)
        reversal_signal: Tuple[int, float],
        volatility_signal: Tuple[int, float],
        macro_signal: Tuple[int, float]
    ) -> Tuple[int, float, str]:
        """
        Gate ensemble signals based on regime.
        
        Returns:
            (action, confidence, source)
        """
        if regime == 'CHAOS':
            # Don't trade in chaos - ignore all signals
            return (0, 0.0, 'CHAOS_VETO')
        
        elif regime == 'TREND':
            # Use trend signal, ignore reversal
            action, conf = trend_signal
            if action == 0:  # Trend says HOLD
                # Check macro for direction
                macro_action, macro_conf = macro_signal
                if macro_conf > 0.7:
                    return (macro_action, macro_conf * 0.8, 'MACRO_TREND')
            return (action, conf, 'TREND')
        
        elif regime == 'RANGE':
            # Use reversal signal, ignore trend
            action, conf = reversal_signal
            return (action, conf, 'REVERSAL')
        
        elif regime == 'CALM':
            # Low vol - only trade high-confidence signals
            # Prefer volatility breakout signals
            vol_action, vol_conf = volatility_signal
            if vol_conf > 0.8:
                return (vol_action, vol_conf, 'VOL_BREAKOUT')
            # Otherwise, light mean reversion
            rev_action, rev_conf = reversal_signal
            if rev_conf > 0.75:
                return (rev_action, rev_conf * 0.8, 'CALM_REVERSAL')
            return (0, 0.5, 'CALM_HOLD')
        
        # Default: HOLD
        return (0, 0.5, 'UNKNOWN_REGIME')
    
    def apply_hard_vetoes(
        self,
        action: int,
        confidence: float,
        liquidity_ok: bool,
        volatility_ok: bool,
        spread_ok: bool,
        expected_move_ok: bool
    ) -> Tuple[int, float, str]:
        """
        Apply hard vetoes from liquidity and volatility agents.
        
        These OVERRIDE the ensemble decision.
        """
        vetoes = []
        
        if self.config.LIQUIDITY_VETO_ENABLED and not liquidity_ok:
            vetoes.append('LIQUIDITY')
        
        if self.config.VOLATILITY_VETO_ENABLED and not volatility_ok:
            vetoes.append('VOLATILITY')
        
        if not spread_ok:
            vetoes.append('SPREAD')
        
        if not expected_move_ok:
            vetoes.append('EXPECTED_MOVE')
        
        if vetoes:
            veto_str = ', '.join(vetoes)
            return (0, 0.0, f'HARD_VETO: {veto_str}')
        
        return (action, confidence, 'PASSED')


# ============================================================================
# MAIN INTEGRATION FUNCTION
# ============================================================================

def run_phase0_phase1_checks(
    symbol: str,
    confidence: float,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
    quote_time: Optional[datetime] = None,
    vix: float = 15.0,
    current_price: Optional[float] = None,
    premium: Optional[float] = None,
    option_volume: Optional[int] = None,
    open_interest: Optional[int] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Run all Phase 0 and Phase 1 checks.
    
    Returns:
        (should_trade, reason, diagnostics)
    """
    gates = Phase0Gates()
    indicators = Phase1Indicators()
    ensemble = Phase1Ensemble()
    
    diagnostics = {
        'phase0_passed': False,
        'phase1_regime': None,
        'vix1d': None,
        'iv_rank': None,
        'expected_move': None,
        'breakeven_move': None,
    }
    
    # Phase 0: Hard gates
    
    # Calculate expected move if we have the data
    expected_move = None
    breakeven_move = None
    
    if current_price is not None:
        vix1d = indicators.get_vix1d()
        diagnostics['vix1d'] = vix1d
        expected_move = indicators.calculate_expected_move(current_price, vix1d)
        diagnostics['expected_move'] = expected_move
        
        if premium is not None:
            breakeven_move = indicators.calculate_breakeven_move(premium)
            diagnostics['breakeven_move'] = breakeven_move
    
    # Run Phase 0 gates
    passed, reason = gates.check_all_gates(
        symbol=symbol,
        confidence=confidence,
        bid=bid,
        ask=ask,
        quote_time=quote_time,
        expected_move=expected_move,
        breakeven_move=breakeven_move,
        option_volume=option_volume,
        open_interest=open_interest
    )
    
    diagnostics['phase0_passed'] = passed
    
    if not passed:
        return False, reason, diagnostics
    
    # Phase 1: Regime detection
    iv_rank = indicators.get_iv_rank(symbol)
    diagnostics['iv_rank'] = iv_rank
    
    vix1d = diagnostics.get('vix1d') or indicators.get_vix1d()
    regime = ensemble.detect_regime(vix, vix1d, iv_rank)
    diagnostics['phase1_regime'] = regime
    
    # Check for CHAOS regime veto
    if regime == 'CHAOS':
        return False, f"❌ P1-VETO: CHAOS regime detected (VIX={vix:.1f})", diagnostics
    
    return True, f"✅ All checks passed (regime={regime})", diagnostics


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'Phase0Config',
    'Phase1Config', 
    'Phase0Gates',
    'Phase1Indicators',
    'Phase1Ensemble',
    'run_phase0_phase1_checks',
    'PHASE0',
    'PHASE1'
]


if __name__ == '__main__':
    # Test the gates
    print("Testing Phase 0 & Phase 1 Gates")
    print("=" * 50)
    
    # Test Phase 0 gates
    gates = Phase0Gates()
    
    # Test 1: Symbol gate
    print("\n1. Symbol Gate Tests:")
    print(f"   SPY: {gates.check_symbol_gate('SPY')}")
    print(f"   QQQ: {gates.check_symbol_gate('QQQ')}")
    print(f"   SPX: {gates.check_symbol_gate('SPX')}")
    print(f"   IWM: {gates.check_symbol_gate('IWM')}")
    
    # Test 2: Confidence gate
    print("\n2. Confidence Gate Tests:")
    print(f"   0.50: {gates.check_confidence_gate(0.50)}")
    print(f"   0.65: {gates.check_confidence_gate(0.65)}")
    print(f"   0.70: {gates.check_confidence_gate(0.70)}")
    print(f"   0.80: {gates.check_confidence_gate(0.80)}")
    
    # Test 3: Spread gate
    print("\n3. Spread Gate Tests:")
    print(f"   Bid=1.00, Ask=1.05: {gates.check_spread_gate(1.00, 1.05)}")
    print(f"   Bid=1.00, Ask=1.20: {gates.check_spread_gate(1.00, 1.20)}")
    print(f"   Bid=0.50, Ask=0.65: {gates.check_spread_gate(0.50, 0.65)}")
    
    # Test 4: Expected move gate
    print("\n4. Expected Move Gate Tests:")
    print(f"   EM=2.0, BE=1.0: {gates.check_expected_move_gate(2.0, 1.0)}")
    print(f"   EM=1.0, BE=1.0: {gates.check_expected_move_gate(1.0, 1.0)}")
    print(f"   EM=0.5, BE=1.0: {gates.check_expected_move_gate(0.5, 1.0)}")
    
    # Test Phase 1 indicators
    print("\n5. Phase 1 Indicator Tests:")
    indicators = Phase1Indicators()
    
    print(f"   VIX1D: {indicators.get_vix1d()}")
    print(f"   IV Rank (SPY): {indicators.get_iv_rank('SPY')}")
    print(f"   Expected Move ($500, IV=15%): ${indicators.calculate_expected_move(500, 15):.2f}")
    
    # Test Phase 1 ensemble
    print("\n6. Regime Detection Tests:")
    ensemble = Phase1Ensemble()
    
    print(f"   VIX=10: {ensemble.detect_regime(10)}")
    print(f"   VIX=15: {ensemble.detect_regime(15)}")
    print(f"   VIX=20: {ensemble.detect_regime(20)}")
    print(f"   VIX=30: {ensemble.detect_regime(30)}")

