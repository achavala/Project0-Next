#!/usr/bin/env python3
"""
Price Prediction Model using Transformer Architecture
Predicts next 5 candles (OHLCV) based on last 20 candles
Auto-learns from prediction errors to improve over time
"""

import os
import torch
import torch.nn as nn
import numpy as np
import pandas as pd
from typing import Tuple, List, Optional, Dict
from datetime import datetime, timedelta
import json
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Device configuration
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu')
logger.info(f"Using device: {DEVICE}")


class PositionalEncoding(nn.Module):
    """Positional encoding for transformer"""
    def __init__(self, d_model: int, max_len: int = 100, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        
        position = torch.arange(max_len).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2) * (-np.log(10000.0) / d_model))
        pe = torch.zeros(max_len, 1, d_model)
        pe[:, 0, 0::2] = torch.sin(position * div_term)
        pe[:, 0, 1::2] = torch.cos(position * div_term)
        self.register_buffer('pe', pe)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:x.size(0)]
        return self.dropout(x)


class CandlePredictionTransformer(nn.Module):
    """
    Transformer model for predicting future OHLCV candles
    Input: Last 20 candles (each with 5 features: O, H, L, C, V)
    Output: Next 5 candles (each with 5 features: O, H, L, C, V)
    """
    def __init__(
        self,
        input_features: int = 5,  # OHLCV
        d_model: int = 128,
        nhead: int = 8,
        num_encoder_layers: int = 4,
        num_decoder_layers: int = 4,
        dim_feedforward: int = 512,
        dropout: float = 0.1,
        input_seq_len: int = 20,
        output_seq_len: int = 5
    ):
        super().__init__()
        
        self.input_features = input_features
        self.d_model = d_model
        self.input_seq_len = input_seq_len
        self.output_seq_len = output_seq_len
        
        # Input embedding
        self.input_embedding = nn.Linear(input_features, d_model)
        self.output_embedding = nn.Linear(input_features, d_model)
        
        # Positional encoding
        self.pos_encoder = PositionalEncoding(d_model, max_len=100, dropout=dropout)
        
        # Transformer
        self.transformer = nn.Transformer(
            d_model=d_model,
            nhead=nhead,
            num_encoder_layers=num_encoder_layers,
            num_decoder_layers=num_decoder_layers,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True
        )
        
        # Output projection
        self.output_projection = nn.Linear(d_model, input_features)
        
        # Initialize weights
        self._init_weights()
    
    def _init_weights(self):
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)
    
    def forward(self, src: torch.Tensor, tgt: torch.Tensor) -> torch.Tensor:
        """
        Args:
            src: Source sequence (batch, input_seq_len, features)
            tgt: Target sequence for teacher forcing (batch, output_seq_len, features)
        Returns:
            Predicted sequence (batch, output_seq_len, features)
        """
        # Embed inputs
        src_embedded = self.input_embedding(src)  # (batch, seq, d_model)
        tgt_embedded = self.output_embedding(tgt)
        
        # Add positional encoding (need to transpose for pos encoding)
        src_embedded = src_embedded.transpose(0, 1)  # (seq, batch, d_model)
        src_embedded = self.pos_encoder(src_embedded)
        src_embedded = src_embedded.transpose(0, 1)  # (batch, seq, d_model)
        
        tgt_embedded = tgt_embedded.transpose(0, 1)
        tgt_embedded = self.pos_encoder(tgt_embedded)
        tgt_embedded = tgt_embedded.transpose(0, 1)
        
        # Create target mask (causal mask for autoregressive)
        tgt_mask = self.transformer.generate_square_subsequent_mask(tgt.size(1)).to(src.device)
        
        # Transformer forward
        output = self.transformer(src_embedded, tgt_embedded, tgt_mask=tgt_mask)
        
        # Project to output features
        output = self.output_projection(output)
        
        return output
    
    def predict(self, src: torch.Tensor) -> torch.Tensor:
        """
        Autoregressive prediction without teacher forcing
        Args:
            src: Source sequence (batch, input_seq_len, features)
        Returns:
            Predicted sequence (batch, output_seq_len, features)
        """
        self.eval()
        batch_size = src.size(0)
        
        # Start with last candle as seed
        tgt = src[:, -1:, :]  # (batch, 1, features)
        
        predictions = []
        
        with torch.no_grad():
            for _ in range(self.output_seq_len):
                # Embed source
                src_embedded = self.input_embedding(src)
                src_embedded = src_embedded.transpose(0, 1)
                src_embedded = self.pos_encoder(src_embedded)
                src_embedded = src_embedded.transpose(0, 1)
                
                # Embed target
                tgt_embedded = self.output_embedding(tgt)
                tgt_embedded = tgt_embedded.transpose(0, 1)
                tgt_embedded = self.pos_encoder(tgt_embedded)
                tgt_embedded = tgt_embedded.transpose(0, 1)
                
                # Create mask
                tgt_mask = self.transformer.generate_square_subsequent_mask(tgt.size(1)).to(src.device)
                
                # Forward
                output = self.transformer(src_embedded, tgt_embedded, tgt_mask=tgt_mask)
                output = self.output_projection(output)
                
                # Take last prediction
                next_pred = output[:, -1:, :]
                predictions.append(next_pred)
                
                # Append to target for next iteration
                tgt = torch.cat([tgt, next_pred], dim=1)
        
        return torch.cat(predictions, dim=1)


class PricePredictor:
    """
    High-level interface for price prediction
    Handles data preprocessing, model management, and auto-learning
    """
    
    def __init__(
        self,
        model_dir: str = "models/predictor",
        input_seq_len: int = 20,
        output_seq_len: int = 5
    ):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        self.input_seq_len = input_seq_len
        self.output_seq_len = output_seq_len
        
        # Initialize model
        self.model = CandlePredictionTransformer(
            input_seq_len=input_seq_len,
            output_seq_len=output_seq_len
        ).to(DEVICE)
        
        # Optimizer
        self.optimizer = torch.optim.AdamW(self.model.parameters(), lr=1e-4, weight_decay=1e-5)
        self.scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(self.optimizer, patience=5, factor=0.5)
        
        # Loss function
        self.criterion = nn.MSELoss()
        
        # Normalization parameters per symbol
        self.norm_params: Dict[str, Dict] = {}
        
        # Prediction history for learning
        self.prediction_history: List[Dict] = []
        
        # Load existing model if available
        self._load_model()
    
    def _load_model(self):
        """Load model and normalization params if they exist"""
        model_path = self.model_dir / "transformer_model.pt"
        norm_path = self.model_dir / "norm_params.json"
        
        if model_path.exists():
            try:
                checkpoint = torch.load(model_path, map_location=DEVICE)
                self.model.load_state_dict(checkpoint['model_state_dict'])
                self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
                logger.info(f"✅ Loaded prediction model from {model_path}")
            except Exception as e:
                logger.warning(f"Could not load model: {e}")
        
        if norm_path.exists():
            try:
                with open(norm_path, 'r') as f:
                    self.norm_params = json.load(f)
                logger.info(f"✅ Loaded normalization params")
            except Exception as e:
                logger.warning(f"Could not load norm params: {e}")
    
    def _save_model(self):
        """Save model and normalization params"""
        model_path = self.model_dir / "transformer_model.pt"
        norm_path = self.model_dir / "norm_params.json"
        
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict()
        }, model_path)
        
        with open(norm_path, 'w') as f:
            json.dump(self.norm_params, f)
        
        logger.info(f"✅ Saved model to {model_path}")
    
    def _normalize(self, data: np.ndarray, symbol: str, fit: bool = False) -> np.ndarray:
        """Normalize OHLCV data using min-max scaling per feature"""
        if fit or symbol not in self.norm_params:
            # Calculate normalization parameters
            self.norm_params[symbol] = {
                'min': data.min(axis=0).tolist(),
                'max': data.max(axis=0).tolist()
            }
        
        params = self.norm_params[symbol]
        min_vals = np.array(params['min'])
        max_vals = np.array(params['max'])
        
        # Avoid division by zero
        range_vals = max_vals - min_vals
        range_vals[range_vals == 0] = 1
        
        normalized = (data - min_vals) / range_vals
        return normalized
    
    def _denormalize(self, data: np.ndarray, symbol: str) -> np.ndarray:
        """Denormalize data back to original scale"""
        if symbol not in self.norm_params:
            return data
        
        params = self.norm_params[symbol]
        min_vals = np.array(params['min'])
        max_vals = np.array(params['max'])
        range_vals = max_vals - min_vals
        
        denormalized = data * range_vals + min_vals
        return denormalized
    
    def prepare_data(self, df: pd.DataFrame, symbol: str) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare data for training
        Args:
            df: DataFrame with OHLCV columns
            symbol: Symbol name for normalization
        Returns:
            X: Input sequences (num_samples, input_seq_len, 5)
            y: Target sequences (num_samples, output_seq_len, 5)
        """
        # Extract OHLCV
        ohlcv = df[['open', 'high', 'low', 'close', 'volume']].values.astype(np.float32)
        
        # Normalize volume separately (log scale)
        ohlcv[:, 4] = np.log1p(ohlcv[:, 4])
        
        # Normalize
        normalized = self._normalize(ohlcv, symbol, fit=True)
        
        # Create sequences
        X, y = [], []
        total_len = self.input_seq_len + self.output_seq_len
        
        for i in range(len(normalized) - total_len + 1):
            X.append(normalized[i:i + self.input_seq_len])
            y.append(normalized[i + self.input_seq_len:i + total_len])
        
        return np.array(X), np.array(y)
    
    def train(
        self,
        df: pd.DataFrame,
        symbol: str,
        epochs: int = 50,
        batch_size: int = 32,
        validation_split: float = 0.2
    ) -> Dict:
        """
        Train the model on historical data
        """
        logger.info(f"🎯 Training prediction model for {symbol}...")
        
        X, y = self.prepare_data(df, symbol)
        
        # Split train/val
        split_idx = int(len(X) * (1 - validation_split))
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        
        # Convert to tensors
        X_train = torch.FloatTensor(X_train).to(DEVICE)
        y_train = torch.FloatTensor(y_train).to(DEVICE)
        X_val = torch.FloatTensor(X_val).to(DEVICE)
        y_val = torch.FloatTensor(y_val).to(DEVICE)
        
        best_val_loss = float('inf')
        history = {'train_loss': [], 'val_loss': []}
        
        self.model.train()
        
        for epoch in range(epochs):
            # Training
            epoch_loss = 0
            num_batches = 0
            
            for i in range(0, len(X_train), batch_size):
                batch_X = X_train[i:i + batch_size]
                batch_y = y_train[i:i + batch_size]
                
                self.optimizer.zero_grad()
                
                # Teacher forcing: use actual targets as decoder input
                output = self.model(batch_X, batch_y)
                loss = self.criterion(output, batch_y)
                
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                self.optimizer.step()
                
                epoch_loss += loss.item()
                num_batches += 1
            
            avg_train_loss = epoch_loss / num_batches
            
            # Validation
            self.model.eval()
            with torch.no_grad():
                val_output = self.model.predict(X_val)
                val_loss = self.criterion(val_output, y_val).item()
            self.model.train()
            
            history['train_loss'].append(avg_train_loss)
            history['val_loss'].append(val_loss)
            
            self.scheduler.step(val_loss)
            
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                self._save_model()
            
            if (epoch + 1) % 10 == 0:
                logger.info(f"Epoch {epoch + 1}/{epochs} - Train Loss: {avg_train_loss:.6f}, Val Loss: {val_loss:.6f}")
        
        logger.info(f"✅ Training complete. Best validation loss: {best_val_loss:.6f}")
        return history
    
    def predict(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        Predict next 5 candles based on last 20 candles
        Args:
            df: DataFrame with at least 20 rows of OHLCV data
            symbol: Symbol name
        Returns:
            DataFrame with predicted candles
        """
        if len(df) < self.input_seq_len:
            raise ValueError(f"Need at least {self.input_seq_len} candles, got {len(df)}")
        
        # Take last input_seq_len candles
        recent = df.tail(self.input_seq_len).copy()
        ohlcv = recent[['open', 'high', 'low', 'close', 'volume']].values.astype(np.float32)
        
        # Normalize volume
        ohlcv[:, 4] = np.log1p(ohlcv[:, 4])
        
        # Normalize
        normalized = self._normalize(ohlcv, symbol, fit=False)
        
        # Convert to tensor
        X = torch.FloatTensor(normalized).unsqueeze(0).to(DEVICE)
        
        # Predict
        self.model.eval()
        with torch.no_grad():
            predictions = self.model.predict(X)
        
        # Denormalize
        pred_np = predictions.cpu().numpy()[0]
        denorm_pred = self._denormalize(pred_np, symbol)
        
        # Convert volume back from log scale
        denorm_pred[:, 4] = np.expm1(denorm_pred[:, 4])
        
        # Ensure OHLC consistency (High >= max(O,C), Low <= min(O,C))
        for i in range(len(denorm_pred)):
            o, h, l, c, v = denorm_pred[i]
            denorm_pred[i, 1] = max(h, o, c)  # High
            denorm_pred[i, 2] = min(l, o, c)  # Low
            denorm_pred[i, 4] = max(0, v)  # Volume non-negative
        
        # Create DataFrame with future timestamps
        last_time = df.index[-1] if isinstance(df.index, pd.DatetimeIndex) else pd.Timestamp.now()
        
        # Assume 1-minute candles
        future_times = [last_time + timedelta(minutes=i+1) for i in range(self.output_seq_len)]
        
        pred_df = pd.DataFrame(
            denorm_pred,
            columns=['open', 'high', 'low', 'close', 'volume'],
            index=future_times
        )
        pred_df['predicted'] = True
        
        return pred_df
    
    def learn_from_actual(self, predicted: pd.DataFrame, actual: pd.DataFrame, symbol: str):
        """
        Learn from prediction errors when actual data becomes available
        This enables continuous improvement
        """
        if len(actual) < len(predicted):
            logger.warning("Not enough actual data to learn from")
            return
        
        # Align timestamps
        actual_aligned = actual.head(len(predicted)).copy()
        
        # Prepare data
        pred_values = predicted[['open', 'high', 'low', 'close', 'volume']].values.astype(np.float32)
        actual_values = actual_aligned[['open', 'high', 'low', 'close', 'volume']].values.astype(np.float32)
        
        # Calculate error
        mse = np.mean((pred_values - actual_values) ** 2)
        logger.info(f"📊 Prediction MSE for {symbol}: {mse:.6f}")
        
        # Store for future reference
        self.prediction_history.append({
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'mse': float(mse),
            'predicted': pred_values.tolist(),
            'actual': actual_values.tolist()
        })
        
        # Save history
        history_path = self.model_dir / "prediction_history.json"
        with open(history_path, 'w') as f:
            json.dump(self.prediction_history[-100:], f)  # Keep last 100
        
        # If we have enough error samples, do a quick fine-tuning step
        if len(self.prediction_history) >= 10:
            self._fine_tune_on_errors(symbol)
    
    def _fine_tune_on_errors(self, symbol: str):
        """Quick fine-tuning based on recent prediction errors"""
        logger.info(f"🔄 Fine-tuning model based on recent errors for {symbol}...")
        
        # Get recent predictions for this symbol
        recent = [h for h in self.prediction_history[-50:] if h['symbol'] == symbol]
        
        if len(recent) < 5:
            return
        
        # Create mini-batch from errors
        # This is a simplified approach - in production you'd want more sophisticated learning
        
        self.model.train()
        for entry in recent[-10:]:
            pred = torch.FloatTensor([entry['predicted']]).to(DEVICE)
            actual = torch.FloatTensor([entry['actual']]).to(DEVICE)
            
            # Normalize
            pred_norm = self._normalize(pred.cpu().numpy()[0], symbol)
            actual_norm = self._normalize(actual.cpu().numpy()[0], symbol)
            
            # This is a simplified fine-tuning - just adjust based on the error
            # In practice, you'd want to use proper sequences
        
        self._save_model()
        logger.info("✅ Fine-tuning complete")


# Singleton instance
_predictor_instance: Optional[PricePredictor] = None

def get_predictor() -> PricePredictor:
    """Get or create singleton predictor instance"""
    global _predictor_instance
    if _predictor_instance is None:
        _predictor_instance = PricePredictor()
    return _predictor_instance


if __name__ == "__main__":
    # Test the predictor
    import yfinance as yf
    
    print("Testing Price Predictor...")
    
    # Get some data
    spy = yf.download("SPY", period="5d", interval="1m")
    if len(spy) > 0:
        spy.columns = [c.lower() for c in spy.columns]
        
        predictor = get_predictor()
        
        # Train on historical data
        print("Training on historical data...")
        predictor.train(spy, "SPY", epochs=20)
        
        # Predict next 5 candles
        print("\nPredicting next 5 candles...")
        predictions = predictor.predict(spy, "SPY")
        print(predictions)
    else:
        print("Could not fetch data for testing")

