#!/usr/bin/env python3
"""
Train the Price Prediction Model on Historical Data
Downloads historical data and trains the Transformer model
"""

import os
import sys
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from price_predictor import PricePredictor, get_predictor


def download_historical_data(symbol: str, days: int = 30) -> pd.DataFrame:
    """Download historical minute data for training"""
    print(f"📥 Downloading {days} days of data for {symbol}...")
    
    # Try yfinance first (easiest)
    try:
        import yfinance as yf
        
        # yfinance only allows 7 days of 1m data at a time
        all_data = []
        
        # Download in chunks
        end_date = datetime.now()
        
        for i in range(0, min(days, 30), 7):
            chunk_end = end_date - timedelta(days=i)
            chunk_start = chunk_end - timedelta(days=7)
            
            data = yf.download(
                symbol,
                start=chunk_start.strftime('%Y-%m-%d'),
                end=chunk_end.strftime('%Y-%m-%d'),
                interval="1m",
                progress=False
            )
            
            if len(data) > 0:
                all_data.append(data)
        
        if all_data:
            combined = pd.concat(all_data)
            combined = combined.sort_index()
            combined = combined[~combined.index.duplicated(keep='first')]
            
            # Normalize column names
            combined.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in combined.columns]
            
            print(f"   ✅ Downloaded {len(combined)} candles")
            return combined
    except Exception as e:
        print(f"   ⚠️ yfinance error: {e}")
    
    # Try Alpaca
    try:
        import config
        from alpaca_trade_api import REST
        
        api = REST(
            config.ALPACA_KEY,
            config.ALPACA_SECRET,
            config.ALPACA_BASE_URL
        )
        
        bars = api.get_bars(
            symbol,
            '1Min',
            limit=10000  # Max allowed
        ).df
        
        if len(bars) > 0:
            bars.columns = [c.lower() for c in bars.columns]
            print(f"   ✅ Downloaded {len(bars)} candles from Alpaca")
            return bars
    except Exception as e:
        print(f"   ⚠️ Alpaca error: {e}")
    
    # Try Massive/Polygon
    try:
        from massive_api_client import MassiveAPIClient
        client = MassiveAPIClient()
        
        data = client.get_historical_data(
            symbol,
            start_date=(datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d'),
            end_date=datetime.now().strftime('%Y-%m-%d'),
            timeframe='1m'
        )
        
        if data is not None and len(data) > 0:
            print(f"   ✅ Downloaded {len(data)} candles from Massive")
            return data
    except Exception as e:
        print(f"   ⚠️ Massive API error: {e}")
    
    print(f"   ❌ Could not download data for {symbol}")
    return pd.DataFrame()


def train_model(symbols: list, epochs: int = 100, days: int = 30):
    """Train the prediction model on multiple symbols"""
    print("=" * 60)
    print("🧠 PRICE PREDICTION MODEL TRAINING")
    print("=" * 60)
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Epochs: {epochs}")
    print(f"Data: Last {days} days")
    print("=" * 60)
    
    predictor = get_predictor()
    
    for symbol in symbols:
        print(f"\n{'='*40}")
        print(f"Training on {symbol}")
        print(f"{'='*40}")
        
        # Download data
        data = download_historical_data(symbol, days)
        
        if len(data) < 100:
            print(f"⚠️ Not enough data for {symbol} (got {len(data)} candles)")
            continue
        
        # Train
        print(f"\n🎯 Training model for {symbol}...")
        history = predictor.train(
            data,
            symbol,
            epochs=epochs,
            batch_size=64,
            validation_split=0.2
        )
        
        print(f"\n📊 Training Results for {symbol}:")
        print(f"   Final Train Loss: {history['train_loss'][-1]:.6f}")
        print(f"   Final Val Loss: {history['val_loss'][-1]:.6f}")
        
        # Test prediction
        print(f"\n🔮 Testing prediction for {symbol}...")
        try:
            predictions = predictor.predict(data, symbol)
            print(f"   Last Price: ${data['close'].iloc[-1]:.2f}")
            print(f"   Predicted (20 candles):")
            for i, (_, row) in enumerate(predictions.iterrows()):
                print(f"      T+{i+1}: O=${row['open']:.2f} H=${row['high']:.2f} L=${row['low']:.2f} C=${row['close']:.2f}")
        except Exception as e:
            print(f"   ⚠️ Prediction test failed: {e}")
    
    print("\n" + "=" * 60)
    print("✅ TRAINING COMPLETE")
    print("=" * 60)
    print("\nModel saved to: models/predictor/")
    print("Run prediction dashboard: streamlit run prediction_dashboard.py")


def main():
    parser = argparse.ArgumentParser(description="Train Price Prediction Model")
    parser.add_argument('--symbols', type=str, default='SPY,QQQ', help='Comma-separated symbols')
    parser.add_argument('--epochs', type=int, default=100, help='Training epochs')
    parser.add_argument('--days', type=int, default=30, help='Days of historical data')
    
    args = parser.parse_args()
    
    symbols = [s.strip().upper() for s in args.symbols.split(',')]
    
    train_model(symbols, args.epochs, args.days)


if __name__ == "__main__":
    main()

