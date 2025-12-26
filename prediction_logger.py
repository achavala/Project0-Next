#!/usr/bin/env python3
"""
Prediction Logger and Validator
Logs all predictions and validates against actual results
Provides end-of-day analysis
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass, asdict
import sqlite3

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PredictionRecord:
    """Single prediction record"""
    id: str
    timestamp: str  # When prediction was made
    symbol: str
    
    # Last known price when prediction was made
    current_price: float
    
    # Predicted candles (20 candles)
    predicted_open: List[float]
    predicted_high: List[float]
    predicted_low: List[float]
    predicted_close: List[float]
    predicted_volume: List[float]
    
    # Predicted direction and target
    predicted_direction: str  # BULLISH, BEARISH, NEUTRAL
    predicted_change_pct: float
    predicted_target: float
    
    # Actual results (filled in later)
    actual_open: Optional[List[float]] = None
    actual_high: Optional[List[float]] = None
    actual_low: Optional[List[float]] = None
    actual_close: Optional[List[float]] = None
    actual_volume: Optional[List[float]] = None
    
    # Validation metrics (calculated after actual data)
    direction_correct: Optional[bool] = None
    mse: Optional[float] = None
    mae: Optional[float] = None
    direction_accuracy: Optional[float] = None
    price_accuracy_pct: Optional[float] = None
    validated: bool = False
    validated_at: Optional[str] = None


class PredictionLogger:
    """
    Logs predictions and validates them against actual results
    """
    
    def __init__(self, log_dir: str = "logs/predictions"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Database for predictions
        self.db_path = self.log_dir / "predictions.db"
        self._init_db()
        
        # Daily log file
        self.daily_log_path = self.log_dir / f"predictions_{datetime.now().strftime('%Y%m%d')}.json"
        
        # In-memory cache for today's predictions
        self.today_predictions: List[PredictionRecord] = []
        
        # Load today's predictions if file exists
        self._load_today_predictions()
        
        logger.info(f"✅ Prediction Logger initialized. Log dir: {self.log_dir}")
    
    def _init_db(self):
        """Initialize SQLite database for predictions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                symbol TEXT,
                current_price REAL,
                predicted_open TEXT,
                predicted_high TEXT,
                predicted_low TEXT,
                predicted_close TEXT,
                predicted_volume TEXT,
                predicted_direction TEXT,
                predicted_change_pct REAL,
                predicted_target REAL,
                actual_open TEXT,
                actual_high TEXT,
                actual_low TEXT,
                actual_close TEXT,
                actual_volume TEXT,
                direction_correct INTEGER,
                mse REAL,
                mae REAL,
                direction_accuracy REAL,
                price_accuracy_pct REAL,
                validated INTEGER DEFAULT 0,
                validated_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Index for faster queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON predictions(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON predictions(symbol)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_validated ON predictions(validated)')
        
        conn.commit()
        conn.close()
    
    def _load_today_predictions(self):
        """Load today's predictions from JSON file"""
        if self.daily_log_path.exists():
            try:
                with open(self.daily_log_path, 'r') as f:
                    data = json.load(f)
                    self.today_predictions = [PredictionRecord(**p) for p in data]
                logger.info(f"Loaded {len(self.today_predictions)} predictions for today")
            except Exception as e:
                logger.warning(f"Could not load today's predictions: {e}")
    
    def _save_today_predictions(self):
        """Save today's predictions to JSON file"""
        try:
            with open(self.daily_log_path, 'w') as f:
                json.dump([asdict(p) for p in self.today_predictions], f, indent=2)
        except Exception as e:
            logger.error(f"Could not save predictions: {e}")
    
    def log_prediction(
        self,
        symbol: str,
        current_price: float,
        predictions: pd.DataFrame,
        predicted_direction: str,
        predicted_change_pct: float,
        predicted_target: float
    ) -> str:
        """
        Log a new prediction
        
        Args:
            symbol: Stock symbol (SPY, QQQ)
            current_price: Current price when prediction was made
            predictions: DataFrame with predicted OHLCV (5 rows)
            predicted_direction: BULLISH, BEARISH, NEUTRAL
            predicted_change_pct: Expected % change
            predicted_target: Target price
        
        Returns:
            Prediction ID
        """
        # Generate unique ID
        pred_id = f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{np.random.randint(1000, 9999)}"
        
        record = PredictionRecord(
            id=pred_id,
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            current_price=current_price,
            predicted_open=predictions['open'].tolist(),
            predicted_high=predictions['high'].tolist(),
            predicted_low=predictions['low'].tolist(),
            predicted_close=predictions['close'].tolist(),
            predicted_volume=predictions['volume'].tolist(),
            predicted_direction=predicted_direction,
            predicted_change_pct=predicted_change_pct,
            predicted_target=predicted_target
        )
        
        # Add to today's predictions
        self.today_predictions.append(record)
        
        # Save to JSON
        self._save_today_predictions()
        
        # Save to database
        self._save_to_db(record)
        
        # Log to file
        self._log_to_file(record)
        
        logger.info(f"📝 Logged prediction {pred_id}: {symbol} {predicted_direction} ({predicted_change_pct:+.2f}%)")
        
        return pred_id
    
    def _save_to_db(self, record: PredictionRecord):
        """Save prediction to SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO predictions (
                id, timestamp, symbol, current_price,
                predicted_open, predicted_high, predicted_low, predicted_close, predicted_volume,
                predicted_direction, predicted_change_pct, predicted_target,
                actual_open, actual_high, actual_low, actual_close, actual_volume,
                direction_correct, mse, mae, direction_accuracy, price_accuracy_pct,
                validated, validated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            record.id, record.timestamp, record.symbol, record.current_price,
            json.dumps(record.predicted_open), json.dumps(record.predicted_high),
            json.dumps(record.predicted_low), json.dumps(record.predicted_close),
            json.dumps(record.predicted_volume),
            record.predicted_direction, record.predicted_change_pct, record.predicted_target,
            json.dumps(record.actual_open) if record.actual_open else None,
            json.dumps(record.actual_high) if record.actual_high else None,
            json.dumps(record.actual_low) if record.actual_low else None,
            json.dumps(record.actual_close) if record.actual_close else None,
            json.dumps(record.actual_volume) if record.actual_volume else None,
            1 if record.direction_correct else 0 if record.direction_correct is False else None,
            record.mse, record.mae, record.direction_accuracy, record.price_accuracy_pct,
            1 if record.validated else 0, record.validated_at
        ))
        
        conn.commit()
        conn.close()
    
    def _log_to_file(self, record: PredictionRecord):
        """Append prediction to daily log file in human-readable format"""
        log_file = self.log_dir / f"prediction_log_{datetime.now().strftime('%Y%m%d')}.txt"
        num_candles = len(record.predicted_close)
        
        with open(log_file, 'a') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"PREDICTION: {record.id}\n")
            f.write(f"{'='*80}\n")
            f.write(f"Time: {record.timestamp}\n")
            f.write(f"Symbol: {record.symbol}\n")
            f.write(f"Current Price: ${record.current_price:.2f}\n")
            f.write(f"Direction: {record.predicted_direction}\n")
            f.write(f"Expected Change: {record.predicted_change_pct:+.2f}%\n")
            f.write(f"Target Price: ${record.predicted_target:.2f}\n")
            f.write(f"\nPredicted {num_candles} Candles (T+1 to T+{num_candles}):\n")
            f.write(f"{'─'*80}\n")
            f.write(f"  {'Candle':<8} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10}\n")
            f.write(f"{'─'*80}\n")
            for i in range(num_candles):
                f.write(f"  T+{i+1:<5} ${record.predicted_open[i]:>9.2f} ${record.predicted_high[i]:>9.2f} "
                       f"${record.predicted_low[i]:>9.2f} ${record.predicted_close[i]:>9.2f}\n")
            f.write(f"{'─'*80}\n")
            f.write(f"\n")
    
    def validate_prediction(
        self,
        pred_id: str,
        actual_data: pd.DataFrame
    ) -> Dict:
        """
        Validate a prediction against actual data
        
        Args:
            pred_id: Prediction ID
            actual_data: DataFrame with actual OHLCV data (20 rows)
        
        Returns:
            Validation metrics
        """
        # Find prediction
        record = None
        for p in self.today_predictions:
            if p.id == pred_id:
                record = p
                break
        
        if record is None:
            # Try loading from database
            record = self._load_from_db(pred_id)
        
        if record is None:
            logger.warning(f"Prediction {pred_id} not found")
            return {}
        
        # Get number of candles predicted
        num_candles = len(record.predicted_close)
        
        # Fill in actual data (match the number of predicted candles)
        record.actual_open = actual_data['open'].tolist()[:num_candles]
        record.actual_high = actual_data['high'].tolist()[:num_candles]
        record.actual_low = actual_data['low'].tolist()[:num_candles]
        record.actual_close = actual_data['close'].tolist()[:num_candles]
        record.actual_volume = actual_data['volume'].tolist()[:num_candles]
        
        # Calculate metrics
        pred_close = np.array(record.predicted_close)
        actual_close = np.array(record.actual_close)
        
        # MSE and MAE for close prices
        record.mse = float(np.mean((pred_close - actual_close) ** 2))
        record.mae = float(np.mean(np.abs(pred_close - actual_close)))
        
        # Direction accuracy (per candle)
        pred_direction_per_candle = np.sign(np.diff(np.concatenate([[record.current_price], pred_close])))
        actual_direction_per_candle = np.sign(np.diff(np.concatenate([[record.current_price], actual_close])))
        record.direction_accuracy = float(np.mean(pred_direction_per_candle == actual_direction_per_candle) * 100)
        
        # Overall direction correct
        actual_final_change = (actual_close[-1] - record.current_price) / record.current_price * 100
        actual_direction = "BULLISH" if actual_final_change > 0.05 else "BEARISH" if actual_final_change < -0.05 else "NEUTRAL"
        record.direction_correct = record.predicted_direction == actual_direction
        
        # Price accuracy (how close was final prediction to actual)
        record.price_accuracy_pct = float(100 - abs(pred_close[-1] - actual_close[-1]) / actual_close[-1] * 100)
        
        record.validated = True
        record.validated_at = datetime.now().isoformat()
        
        # Update database
        self._save_to_db(record)
        
        # Update JSON
        self._save_today_predictions()
        
        # Log validation
        self._log_validation(record)
        
        logger.info(f"✅ Validated prediction {pred_id}: Direction {'✓' if record.direction_correct else '✗'}, "
                   f"Accuracy {record.price_accuracy_pct:.1f}%")
        
        return {
            'direction_correct': record.direction_correct,
            'mse': record.mse,
            'mae': record.mae,
            'direction_accuracy': record.direction_accuracy,
            'price_accuracy_pct': record.price_accuracy_pct,
            'predicted_direction': record.predicted_direction,
            'actual_direction': actual_direction,
            'predicted_change': record.predicted_change_pct,
            'actual_change': actual_final_change
        }
    
    def _load_from_db(self, pred_id: str) -> Optional[PredictionRecord]:
        """Load prediction from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM predictions WHERE id = ?', (pred_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        # Convert row to PredictionRecord
        return PredictionRecord(
            id=row[0],
            timestamp=row[1],
            symbol=row[2],
            current_price=row[3],
            predicted_open=json.loads(row[4]),
            predicted_high=json.loads(row[5]),
            predicted_low=json.loads(row[6]),
            predicted_close=json.loads(row[7]),
            predicted_volume=json.loads(row[8]),
            predicted_direction=row[9],
            predicted_change_pct=row[10],
            predicted_target=row[11],
            actual_open=json.loads(row[12]) if row[12] else None,
            actual_high=json.loads(row[13]) if row[13] else None,
            actual_low=json.loads(row[14]) if row[14] else None,
            actual_close=json.loads(row[15]) if row[15] else None,
            actual_volume=json.loads(row[16]) if row[16] else None,
            direction_correct=bool(row[17]) if row[17] is not None else None,
            mse=row[18],
            mae=row[19],
            direction_accuracy=row[20],
            price_accuracy_pct=row[21],
            validated=bool(row[22]),
            validated_at=row[23]
        )
    
    def _log_validation(self, record: PredictionRecord):
        """Log validation results to file"""
        log_file = self.log_dir / f"validation_log_{datetime.now().strftime('%Y%m%d')}.txt"
        num_candles = len(record.predicted_close)
        
        with open(log_file, 'a') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"VALIDATION: {record.id}\n")
            f.write(f"{'='*80}\n")
            f.write(f"Validated At: {record.validated_at}\n")
            f.write(f"Symbol: {record.symbol}\n")
            f.write(f"Prediction Time: {record.timestamp}\n")
            f.write(f"Number of Candles: {num_candles}\n")
            f.write(f"\nPREDICTED:\n")
            f.write(f"  Direction: {record.predicted_direction} ({record.predicted_change_pct:+.2f}%)\n")
            f.write(f"  Target: ${record.predicted_target:.2f}\n")
            f.write(f"\nACTUAL:\n")
            actual_change = (record.actual_close[-1] - record.current_price) / record.current_price * 100
            actual_dir = "BULLISH" if actual_change > 0.05 else "BEARISH" if actual_change < -0.05 else "NEUTRAL"
            f.write(f"  Direction: {actual_dir} ({actual_change:+.2f}%)\n")
            f.write(f"  Final Price: ${record.actual_close[-1]:.2f}\n")
            f.write(f"\nCANDLE COMPARISON (Predicted vs Actual Close):\n")
            f.write(f"{'─'*60}\n")
            for i in range(min(num_candles, len(record.actual_close))):
                pred_c = record.predicted_close[i]
                act_c = record.actual_close[i]
                diff = act_c - pred_c
                diff_pct = (diff / act_c) * 100 if act_c != 0 else 0
                f.write(f"  T+{i+1:<3}: Pred=${pred_c:>8.2f} | Actual=${act_c:>8.2f} | Diff={diff:+.2f} ({diff_pct:+.2f}%)\n")
            f.write(f"{'─'*60}\n")
            f.write(f"\nMETRICS:\n")
            f.write(f"  Direction Correct: {'✓ YES' if record.direction_correct else '✗ NO'}\n")
            f.write(f"  Price Accuracy: {record.price_accuracy_pct:.1f}%\n")
            f.write(f"  Direction Accuracy (per candle): {record.direction_accuracy:.1f}%\n")
            f.write(f"  MSE: {record.mse:.6f}\n")
            f.write(f"  MAE: ${record.mae:.4f}\n")
            f.write(f"\n")
    
    def get_pending_validations(self, symbol: str = None) -> List[PredictionRecord]:
        """Get predictions that haven't been validated yet"""
        predictions = []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if symbol:
            cursor.execute('SELECT id FROM predictions WHERE validated = 0 AND symbol = ?', (symbol,))
        else:
            cursor.execute('SELECT id FROM predictions WHERE validated = 0')
        
        rows = cursor.fetchall()
        conn.close()
        
        for row in rows:
            record = self._load_from_db(row[0])
            if record:
                predictions.append(record)
        
        return predictions
    
    def get_daily_summary(self, date: str = None) -> Dict:
        """
        Get daily prediction summary
        
        Args:
            date: Date in YYYY-MM-DD format (default: today)
        
        Returns:
            Summary statistics
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all predictions for the date
        cursor.execute('''
            SELECT * FROM predictions 
            WHERE DATE(timestamp) = ?
        ''', (date,))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return {'date': date, 'total_predictions': 0}
        
        # Calculate statistics
        total = len(rows)
        validated = sum(1 for r in rows if r[22])  # validated column
        
        # Validated predictions stats
        validated_rows = [r for r in rows if r[22]]
        
        if validated_rows:
            direction_correct = sum(1 for r in validated_rows if r[17])  # direction_correct
            avg_price_accuracy = np.mean([r[21] for r in validated_rows if r[21] is not None])
            avg_direction_accuracy = np.mean([r[20] for r in validated_rows if r[20] is not None])
            avg_mae = np.mean([r[19] for r in validated_rows if r[19] is not None])
        else:
            direction_correct = 0
            avg_price_accuracy = 0
            avg_direction_accuracy = 0
            avg_mae = 0
        
        # By symbol
        symbols = {}
        for row in rows:
            sym = row[2]
            if sym not in symbols:
                symbols[sym] = {'total': 0, 'validated': 0, 'direction_correct': 0}
            symbols[sym]['total'] += 1
            if row[22]:
                symbols[sym]['validated'] += 1
                if row[17]:
                    symbols[sym]['direction_correct'] += 1
        
        return {
            'date': date,
            'total_predictions': total,
            'validated': validated,
            'pending_validation': total - validated,
            'direction_correct': direction_correct,
            'direction_accuracy_pct': (direction_correct / validated * 100) if validated > 0 else 0,
            'avg_price_accuracy_pct': float(avg_price_accuracy) if avg_price_accuracy else 0,
            'avg_candle_direction_accuracy_pct': float(avg_direction_accuracy) if avg_direction_accuracy else 0,
            'avg_mae': float(avg_mae) if avg_mae else 0,
            'by_symbol': symbols
        }
    
    def generate_eod_report(self, date: str = None) -> str:
        """
        Generate end-of-day validation report as Markdown
        
        Args:
            date: Date in YYYY-MM-DD format (default: today)
        
        Returns:
            Report as markdown string
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        summary = self.get_daily_summary(date)
        
        # Build Markdown report
        md = []
        md.append(f"# 📊 Prediction Validation Report")
        md.append(f"## Date: {date}")
        md.append(f"")
        md.append(f"*Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S EST')}*")
        md.append(f"")
        md.append(f"---")
        md.append(f"")
        md.append(f"## 📋 Summary")
        md.append(f"")
        md.append(f"| Metric | Value |")
        md.append(f"|--------|-------|")
        md.append(f"| Total Predictions | {summary['total_predictions']} |")
        md.append(f"| Validated | {summary['validated']} |")
        md.append(f"| Pending Validation | {summary['pending_validation']} |")
        md.append(f"")
        
        if summary['validated'] > 0:
            md.append(f"## 📈 Accuracy Metrics")
            md.append(f"")
            md.append(f"| Metric | Value |")
            md.append(f"|--------|-------|")
            md.append(f"| Direction Correct | {summary['direction_correct']}/{summary['validated']} ({summary['direction_accuracy_pct']:.1f}%) |")
            md.append(f"| Avg Price Accuracy | {summary['avg_price_accuracy_pct']:.1f}% |")
            md.append(f"| Avg Candle Direction Accuracy | {summary['avg_candle_direction_accuracy_pct']:.1f}% |")
            md.append(f"| Avg MAE | ${summary['avg_mae']:.4f} |")
            md.append(f"")
            
            # Performance badge
            accuracy = summary['direction_accuracy_pct']
            if accuracy >= 70:
                badge = "🟢 **EXCELLENT**"
            elif accuracy >= 50:
                badge = "🟡 **GOOD**"
            else:
                badge = "🔴 **NEEDS IMPROVEMENT**"
            md.append(f"### Overall Performance: {badge}")
            md.append(f"")
            
            md.append(f"## 📊 Performance by Symbol")
            md.append(f"")
            md.append(f"| Symbol | Total | Validated | Direction Correct | Accuracy |")
            md.append(f"|--------|-------|-----------|-------------------|----------|")
            for sym, stats in summary['by_symbol'].items():
                if stats['validated'] > 0:
                    acc = stats['direction_correct'] / stats['validated'] * 100
                    emoji = "✅" if acc >= 50 else "❌"
                    md.append(f"| {sym} | {stats['total']} | {stats['validated']} | {stats['direction_correct']} | {emoji} {acc:.1f}% |")
                else:
                    md.append(f"| {sym} | {stats['total']} | 0 | - | ⏳ Pending |")
            md.append(f"")
        else:
            md.append(f"## ⏳ No Validated Predictions Yet")
            md.append(f"")
            md.append(f"Predictions are waiting to be validated against actual market data.")
            md.append(f"")
        
        # Detailed predictions section
        md.append(f"## 📝 Detailed Predictions")
        md.append(f"")
        
        # Get all predictions for the day
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, timestamp, symbol, current_price, predicted_direction, 
                   predicted_change_pct, predicted_target, validated, direction_correct,
                   price_accuracy_pct, predicted_close
            FROM predictions 
            WHERE DATE(timestamp) = ?
            ORDER BY timestamp
        ''', (date,))
        rows = cursor.fetchall()
        conn.close()
        
        if rows:
            md.append(f"| Time | Symbol | Direction | Pred Change | Target | Status | Result |")
            md.append(f"|------|--------|-----------|-------------|--------|--------|--------|")
            for row in rows:
                time_str = row[1].split('T')[1][:8] if 'T' in row[1] else row[1]
                status = "✅ Validated" if row[7] else "⏳ Pending"
                if row[7]:  # validated
                    result = "✅ Correct" if row[8] else "❌ Wrong"
                    result += f" ({row[9]:.1f}%)" if row[9] else ""
                else:
                    result = "-"
                direction_emoji = "📈" if row[4] == "BULLISH" else "📉" if row[4] == "BEARISH" else "➡️"
                md.append(f"| {time_str} | {row[2]} | {direction_emoji} {row[4]} | {row[5]:+.2f}% | ${row[6]:.2f} | {status} | {result} |")
        else:
            md.append(f"*No predictions recorded for this date.*")
        
        md.append(f"")
        md.append(f"---")
        md.append(f"")
        md.append(f"## 🔧 Model Information")
        md.append(f"")
        md.append(f"- **Model Type**: Transformer-based Price Predictor")
        md.append(f"- **Input**: Last 20 candles (1-minute bars)")
        md.append(f"- **Output**: Next 20 candles predicted")
        md.append(f"- **Symbols**: SPY, QQQ")
        md.append(f"")
        md.append(f"---")
        md.append(f"")
        md.append(f"*This report is automatically generated by the Mike Agent Prediction System.*")
        
        report_text = "\n".join(md)
        
        # Save to Markdown file
        report_file = self.log_dir / f"prediction_report_{date.replace('-', '')}.md"
        with open(report_file, 'w') as f:
            f.write(report_text)
        
        # Also save a plain text version for backward compatibility
        txt_report_file = self.log_dir / f"eod_report_{date.replace('-', '')}.txt"
        with open(txt_report_file, 'w') as f:
            # Write plain text version
            plain_report = []
            plain_report.append("=" * 70)
            plain_report.append(f"PREDICTION VALIDATION REPORT - {date}")
            plain_report.append("=" * 70)
            plain_report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S EST')}")
            plain_report.append("")
            plain_report.append(f"Total Predictions: {summary['total_predictions']}")
            plain_report.append(f"Validated: {summary['validated']}")
            plain_report.append(f"Pending Validation: {summary['pending_validation']}")
            if summary['validated'] > 0:
                plain_report.append("")
                plain_report.append("ACCURACY METRICS:")
                plain_report.append(f"  Direction Correct: {summary['direction_correct']}/{summary['validated']} ({summary['direction_accuracy_pct']:.1f}%)")
                plain_report.append(f"  Avg Price Accuracy: {summary['avg_price_accuracy_pct']:.1f}%")
                plain_report.append(f"  Avg Candle Direction Accuracy: {summary['avg_candle_direction_accuracy_pct']:.1f}%")
                plain_report.append(f"  Avg MAE: ${summary['avg_mae']:.4f}")
            plain_report.append("=" * 70)
            f.write("\n".join(plain_report))
        
        logger.info(f"📄 EOD report saved to {report_file}")
        
        return report_text


# Singleton instance
_logger_instance: Optional[PredictionLogger] = None

def get_prediction_logger() -> PredictionLogger:
    """Get or create singleton logger instance"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = PredictionLogger()
    return _logger_instance


if __name__ == "__main__":
    # Test the logger
    pred_logger = get_prediction_logger()
    
    # Create a sample prediction with 20 candles
    import pandas as pd
    
    # Generate 20 candle predictions
    base_price = 100.0
    pred_data = {
        'open': [base_price + i * 0.1 for i in range(20)],
        'high': [base_price + i * 0.1 + 0.2 for i in range(20)],
        'low': [base_price + i * 0.1 - 0.1 for i in range(20)],
        'close': [base_price + i * 0.1 + 0.15 for i in range(20)],
        'volume': [1000 + i * 50 for i in range(20)]
    }
    pred_df = pd.DataFrame(pred_data)
    
    # Log prediction
    pred_id = pred_logger.log_prediction(
        symbol="TEST",
        current_price=base_price,
        predictions=pred_df,
        predicted_direction="BULLISH",
        predicted_change_pct=2.0,
        predicted_target=base_price * 1.02
    )
    
    print(f"Logged prediction: {pred_id}")
    
    # Simulate actual data (20 candles)
    actual_data = {
        'open': [base_price + i * 0.08 for i in range(20)],
        'high': [base_price + i * 0.08 + 0.18 for i in range(20)],
        'low': [base_price + i * 0.08 - 0.08 for i in range(20)],
        'close': [base_price + i * 0.08 + 0.12 for i in range(20)],
        'volume': [1020 + i * 45 for i in range(20)]
    }
    actual_df = pd.DataFrame(actual_data)
    
    # Validate
    metrics = pred_logger.validate_prediction(pred_id, actual_df)
    print(f"Validation metrics: {metrics}")
    
    # Generate report
    report = pred_logger.generate_eod_report()
    print(report)

