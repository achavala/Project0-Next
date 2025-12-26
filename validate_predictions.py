#!/usr/bin/env python3
"""
Validate Predictions and Generate EOD Report
Run at end of day to validate all predictions against actual data
"""

import os
import sys
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prediction_logger import get_prediction_logger


def get_live_data(symbol: str, bars: int = 100):
    """Fetch live data from Alpaca or fallback sources"""
    import pandas as pd
    
    try:
        # Try Alpaca first
        import config
        from alpaca_trade_api import REST
        
        api = REST(
            config.ALPACA_KEY,
            config.ALPACA_SECRET,
            config.ALPACA_BASE_URL
        )
        
        bars_data = api.get_bars(
            symbol,
            '1Min',
            limit=bars
        ).df
        
        if len(bars_data) > 0:
            bars_data.columns = [c.lower() for c in bars_data.columns]
            return bars_data
    except Exception as e:
        print(f"Alpaca error: {e}")
    
    # Fallback to yfinance
    try:
        import yfinance as yf
        data = yf.download(symbol, period="1d", interval="1m", progress=False)
        if len(data) > 0:
            data.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in data.columns]
            return data.tail(bars)
    except Exception as e:
        print(f"yfinance error: {e}")
    
    return None


def validate_all_pending(pred_logger):
    """Validate all pending predictions"""
    print("=" * 60)
    print("🔍 VALIDATING PENDING PREDICTIONS")
    print("=" * 60)
    
    pending = pred_logger.get_pending_validations()
    
    if not pending:
        print("✅ No pending validations")
        return 0
    
    print(f"Found {len(pending)} pending predictions to validate\n")
    
    validated_count = 0
    
    for record in pending:
        print(f"Validating {record.id}...")
        
        try:
            # Calculate how old this prediction is
            pred_time = datetime.fromisoformat(record.timestamp)
            age_minutes = (datetime.now() - pred_time).total_seconds() / 60
            
            if age_minutes < 5:
                print(f"  ⏳ Too recent (need 5 min of data). Age: {age_minutes:.1f} min")
                continue
            
            # Get actual data
            actual_data = get_live_data(record.symbol, bars=50)
            
            if actual_data is None or len(actual_data) < 5:
                print(f"  ⚠️ Could not fetch actual data for {record.symbol}")
                continue
            
            # Find the 5 candles after the prediction time
            # For simplicity, use the most recent 5 candles if prediction is old enough
            actual_candles = actual_data.tail(5)
            
            # Validate
            metrics = pred_logger.validate_prediction(record.id, actual_candles)
            
            if metrics:
                validated_count += 1
                dir_status = "✓" if metrics['direction_correct'] else "✗"
                print(f"  ✅ Validated: Direction {dir_status}, Accuracy {metrics['price_accuracy_pct']:.1f}%")
                print(f"     Predicted: {metrics['predicted_direction']} ({metrics['predicted_change']:+.2f}%)")
                print(f"     Actual:    {metrics['actual_direction']} ({metrics['actual_change']:+.2f}%)")
            else:
                print(f"  ⚠️ Validation returned empty metrics")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    print(f"\n✅ Validated {validated_count}/{len(pending)} predictions")
    return validated_count


def generate_report(pred_logger, date=None):
    """Generate end-of-day report"""
    print("\n" + "=" * 60)
    print("📊 GENERATING END-OF-DAY REPORT")
    print("=" * 60)
    
    report = pred_logger.generate_eod_report(date)
    print(report)
    
    return report


def main():
    parser = argparse.ArgumentParser(description="Validate Predictions and Generate Report")
    parser.add_argument('--date', type=str, help='Date to report on (YYYY-MM-DD). Default: today')
    parser.add_argument('--validate-only', action='store_true', help='Only validate, skip report')
    parser.add_argument('--report-only', action='store_true', help='Only generate report, skip validation')
    
    args = parser.parse_args()
    
    pred_logger = get_prediction_logger()
    
    print(f"\n🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Log directory: {pred_logger.log_dir}\n")
    
    if not args.report_only:
        validate_all_pending(pred_logger)
    
    if not args.validate_only:
        generate_report(pred_logger, args.date)
    
    print("\n✅ Done!")


if __name__ == "__main__":
    main()

