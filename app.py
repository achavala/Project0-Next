import streamlit as st
import datetime
import pytz
import time
import os
import pandas as pd
import numpy as np
import alpaca_trade_api as tradeapi
import config
import yfinance as yf
from datetime import timedelta, date
import plotly.graph_objects as go

# Import trade database
try:
    from trade_database import TradeDatabase
    TRADE_DB_AVAILABLE = True
except ImportError:
    TRADE_DB_AVAILABLE = False

# Import prediction modules
try:
    from price_predictor import get_predictor
    from prediction_logger import get_prediction_logger
    PREDICTION_AVAILABLE = True
except ImportError:
    PREDICTION_AVAILABLE = False

st.set_page_config(page_title="Mike Agent v3 - Unified Dashboard", layout="wide")


# ============================================================================
# PREDICTION TAB FUNCTIONS
# ============================================================================

def get_live_data_for_prediction(symbol: str, bars: int = 100) -> pd.DataFrame:
    """Fetch REAL-TIME live data - Prioritizes Alpaca (real-time with paper trading), then Massive, then yfinance"""
    est = pytz.timezone('US/Eastern')
    now = datetime.datetime.now(est)
    current_time = now.strftime('%H:%M:%S EST')
    today = now.date()
    today_str = today.strftime('%Y-%m-%d')
    
    # ========== PRIORITY 1: ALPACA API (Real-Time with Paper Trading) ==========
    try:
        api = tradeapi.REST(
            config.ALPACA_KEY,
            config.ALPACA_SECRET,
            config.ALPACA_BASE_URL
        )
        
        # Get ALL bars for today (up to 1000) to ensure we get the MOST RECENT data
        # Alpaca returns oldest first, so we need enough to include current time
        bars_data = api.get_bars(
            symbol, 
            '1Min', 
            start=today_str,
            limit=1000  # Get all today's bars
        ).df
        
        if len(bars_data) > 0:
            bars_data.columns = [c.lower() for c in bars_data.columns]
            
            # Convert timezone from UTC to EST
            if bars_data.index.tzinfo is not None:
                bars_data.index = bars_data.index.tz_convert(est)
            else:
                bars_data.index = bars_data.index.tz_localize('UTC').tz_convert(est)
            
            # Get the LATEST data (tail of the dataframe)
            latest_bar = bars_data.index[-1]
            latest_price = bars_data['close'].iloc[-1]
            bar_time_str = latest_bar.strftime('%H:%M EST')
            
            # Check data freshness
            delay_seconds = (now - latest_bar).total_seconds()
            delay_minutes = delay_seconds / 60
            
            # Check if market is open (9:30 AM - 4:00 PM EST)
            market_open = 9.5 <= now.hour + (now.minute / 60) < 16.0
            
            if market_open and delay_minutes < 5:
                status = "📡 REAL-TIME (Alpaca)"
            elif market_open and delay_minutes < 20:
                status = f"📡 Alpaca ({delay_minutes:.0f}m)"
            elif not market_open:
                status = f"📡 Alpaca (Closed)"
            else:
                status = f"⏳ Alpaca ({delay_minutes:.0f}m old)"
            
            st.caption(f"{status}: {symbol} @ ${latest_price:.2f} | Latest: {bar_time_str} | Now: {current_time}")
            return bars_data.tail(bars)  # Return the MOST RECENT bars
            
    except Exception as e:
        pass  # Fall through to next source
    
    # ========== PRIORITY 2: MASSIVE/POLYGON API (May be 15-min delayed) ==========
    try:
        from massive_api_client import MassiveAPIClient
        massive_client = MassiveAPIClient()
        
        # Get today's data from Massive API
        end_date_str = (now + timedelta(days=1)).strftime('%Y-%m-%d')
        data = massive_client.get_historical_data(symbol, today_str, end_date_str, interval='1m')
        
        if data is not None and len(data) > 0:
            data.columns = [c.lower() for c in data.columns]
            
            # Massive API returns timestamps in UTC - convert to EST
            if data.index.tzinfo is None:
                data.index = data.index.tz_localize('UTC').tz_convert('US/Eastern')
            else:
                data.index = data.index.tz_convert('US/Eastern')
            
            # Filter to today's data only
            data = data[data.index.date == today]
            
            if len(data) > 0:
                latest_bar_time = data.index[-1]
                latest_price = data['close'].iloc[-1]
                bar_time_str = latest_bar_time.strftime('%H:%M EST')
                
                # Check data freshness
                delay_seconds = (now - latest_bar_time).total_seconds()
                delay_minutes = delay_seconds / 60
                
                if delay_minutes > 10:
                    status = f"⏳ Massive API ({delay_minutes:.0f}m delayed)"
                else:
                    status = "📡 Massive API"
                
                st.caption(f"{status}: {symbol} @ ${latest_price:.2f} | Latest: {bar_time_str} | Now: {current_time}")
                return data.tail(bars)
    except Exception as e:
        pass  # Fall through to yfinance
    
    # ========== PRIORITY 3: YFINANCE (Fallback) ==========
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d", interval="1m")
        
        if len(data) > 0:
            data.columns = [c.lower() for c in data.columns]
            
            # Make sure timezone is EST
            if data.index.tzinfo is None:
                data.index = data.index.tz_localize('US/Eastern')
            else:
                data.index = data.index.tz_convert('US/Eastern')
            
            latest_bar_time = data.index[-1]
            latest_price = data['close'].iloc[-1]
            bar_time_str = latest_bar_time.strftime('%H:%M EST')
            bar_date = latest_bar_time.strftime('%Y-%m-%d')
            
            if bar_date == today_str:
                st.caption(f"📡 yfinance: {symbol} @ ${latest_price:.2f} | Latest: {bar_time_str} | Now: {current_time}")
            else:
                st.caption(f"⏳ yfinance: {symbol} @ ${latest_price:.2f} | Last: {bar_date} {bar_time_str}")
            
            return data.tail(bars)
            
    except Exception as e:
        st.warning(f"⚠️ yfinance error for {symbol}: {e}")
    
    st.error(f"❌ All data sources failed for {symbol}")
    return pd.DataFrame()


def create_prediction_candlestick(df: pd.DataFrame, predictions: pd.DataFrame, symbol: str) -> go.Figure:
    """Create candlestick chart with predictions"""
    df_20 = df.tail(20).copy()
    
    fig = go.Figure()
    
    # Historical candles
    fig.add_trace(go.Candlestick(
        x=list(range(len(df_20))),
        open=df_20['open'],
        high=df_20['high'],
        low=df_20['low'],
        close=df_20['close'],
        name='Last 20 Candles',
        increasing_line_color='#00ff88',
        decreasing_line_color='#ff4444',
        increasing_fillcolor='#00ff88',
        decreasing_fillcolor='#ff4444'
    ))
    
    # Predicted candles
    if predictions is not None and len(predictions) > 0:
        pred_x = list(range(len(df_20), len(df_20) + len(predictions)))
        
        fig.add_trace(go.Candlestick(
            x=pred_x,
            open=predictions['open'],
            high=predictions['high'],
            low=predictions['low'],
            close=predictions['close'],
            name='Predicted 20 Candles',
            increasing_line_color='#00ff88',  # Same green as real candles
            decreasing_line_color='#ff4444',  # Same red as real candles
            increasing_fillcolor='#00ff88',   # Green fill for up candles
            decreasing_fillcolor='#ff4444'    # Red fill for down candles
        ))
        
        fig.add_vline(x=len(df_20) - 0.5, line_dash="dash", line_color="cyan",
                      annotation_text="NOW", annotation_position="top")
        
        # Calculate direction
        last_close = df_20['close'].iloc[-1]
        pred_close = predictions['close'].iloc[-1]
        pct_change = ((pred_close - last_close) / last_close) * 100
        direction = "📈 BULLISH" if pct_change > 0.05 else "📉 BEARISH" if pct_change < -0.05 else "➡️ NEUTRAL"
        color = "#00ff88" if pct_change > 0 else "#ff4444" if pct_change < 0 else "#ffaa00"
        
        fig.add_annotation(
            x=len(df_20) + 2, y=predictions['high'].max(),
            text=f"{direction}<br>{pct_change:+.2f}%",
            showarrow=False, font=dict(size=12, color=color),
            bgcolor="rgba(0,0,0,0.7)", bordercolor=color
        )
    
    x_labels = [f"T-{20-i}" for i in range(20)] + [f"T+{i+1}" for i in range(5)]
    
    fig.update_layout(
        title=dict(text=f"🔮 {symbol}: Last 20 → Next 20 Candles", font=dict(size=16, color='white'), x=0.5),
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0.3)',
        xaxis=dict(tickmode='array', tickvals=list(range(25)), ticktext=x_labels, tickangle=45, rangeslider=dict(visible=False)),
        yaxis=dict(title='Price ($)'),
        height=400,
        margin=dict(l=50, r=50, t=50, b=80),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    return fig


def create_simple_candlestick(df: pd.DataFrame, title: str) -> go.Figure:
    """Create simple candlestick chart with actual timestamps"""
    df_plot = df.tail(50).copy()
    
    # Ensure index is in EST timezone before plotting
    # Data from Massive API is in UTC - convert to EST
    if df_plot.index.tzinfo is None:
        # Assume UTC if no timezone (Massive API returns UTC)
        df_plot.index = df_plot.index.tz_localize('UTC').tz_convert('US/Eastern')
    else:
        df_plot.index = df_plot.index.tz_convert('US/Eastern')
    
    # Use actual datetime index for x-axis
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df_plot.index,  # Use actual timestamps
        open=df_plot['open'],
        high=df_plot['high'],
        low=df_plot['low'],
        close=df_plot['close'],
        increasing_line_color='#00ff88',
        decreasing_line_color='#ff4444',
        increasing_fillcolor='#00ff88',
        decreasing_fillcolor='#ff4444'
    ))
    
    # Get current time and latest data time
    est = pytz.timezone('US/Eastern')
    current_time = datetime.datetime.now(est).strftime('%H:%M:%S EST')
    
    # Get latest bar time from actual data - ensure it's displayed in EST
    if len(df_plot) > 0:
        latest_bar_ts = df_plot.index[-1]
        latest_price = df_plot['close'].iloc[-1]
        
        # Ensure timestamp is converted to EST timezone before formatting
        # Data should already be in EST from conversion above, but verify
        if hasattr(latest_bar_ts, 'tz_localize'):
            # pandas Timestamp
            if latest_bar_ts.tzinfo is None:
                # Assume UTC if naive, convert to EST
                latest_bar_ts = latest_bar_ts.tz_localize('UTC').tz_convert('US/Eastern')
            else:
                latest_bar_ts = latest_bar_ts.tz_convert('US/Eastern')
        elif hasattr(latest_bar_ts, 'astimezone'):
            # datetime object
            if latest_bar_ts.tzinfo is None:
                # Assume UTC if naive
                latest_bar_ts = pytz.UTC.localize(latest_bar_ts).astimezone(est)
            else:
                latest_bar_ts = latest_bar_ts.astimezone(est)
        
        # Format in EST (timestamp is now guaranteed to be in EST)
        latest_bar = latest_bar_ts.strftime('%H:%M EST')
        subtitle = f"Latest bar: {latest_bar} | Price: ${latest_price:.2f}"
    else:
        subtitle = f"Update: {current_time}"
    
    fig.update_layout(
        title=dict(text=f"{title}<br><sub style='color:#888'>{subtitle}</sub>", 
                   font=dict(size=16, color='white'), x=0.5),
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0.3)',
        xaxis=dict(
            rangeslider=dict(visible=False), 
            title='Time (EST)',
            tickformat='%H:%M',  # Format as HH:MM
            tickangle=45
        ),
        yaxis=dict(title='Price ($)'),
        height=350,
        margin=dict(l=50, r=50, t=70, b=70)
    )
    
    return fig


def render_prediction_tab():
    """Render the prediction tab content"""
    st.markdown("<h2 style='text-align: center;'>🔮 Price Predictions</h2>", unsafe_allow_html=True)
    st.caption("Transformer-based model predicting next 20 candles from last 20")
    
    # Initialize predictor and logger
    try:
        predictor = get_predictor()
        pred_logger = get_prediction_logger()
    except Exception as e:
        st.error(f"Could not initialize prediction system: {e}")
        return
    
    # Handle retrain request
    if st.session_state.get('retrain_model', False):
        with st.spinner("Retraining model..."):
            spy_data = get_live_data_for_prediction("SPY", bars=500)
            qqq_data = get_live_data_for_prediction("QQQ", bars=500)
            if len(spy_data) > 100:
                predictor.train(spy_data, "SPY", epochs=30)
            if len(qqq_data) > 100:
                predictor.train(qqq_data, "QQQ", epochs=30)
            st.success("✅ Model retrained!")
        st.session_state.retrain_model = False
    
    # Handle validation request
    if st.session_state.get('validate_pending', False):
        validate_pending_predictions(pred_logger)
        st.session_state.validate_pending = False
    
    # Fetch data
    with st.spinner("Fetching market data..."):
        spy_data = get_live_data_for_prediction("SPY", bars=100)
        qqq_data = get_live_data_for_prediction("QQQ", bars=100)
    
    if len(spy_data) == 0 or len(qqq_data) == 0:
        st.error("❌ Could not fetch market data")
        return
    
    # Make predictions with validation
    try:
        # Get the last 20 candles being used as input
        spy_last_20 = spy_data.tail(20)
        qqq_last_20 = qqq_data.tail(20)
        
        # Show what data is being used for prediction
        spy_input_start = spy_last_20['close'].iloc[0]
        spy_input_end = spy_last_20['close'].iloc[-1]
        qqq_input_start = qqq_last_20['close'].iloc[0]
        qqq_input_end = qqq_last_20['close'].iloc[-1]
        
        st.caption(f"🔍 **SPY Input:** Last 20 bars from ${spy_input_start:.2f} → ${spy_input_end:.2f} (Δ {((spy_input_end/spy_input_start)-1)*100:+.2f}%)")
        st.caption(f"🔍 **QQQ Input:** Last 20 bars from ${qqq_input_start:.2f} → ${qqq_input_end:.2f} (Δ {((qqq_input_end/qqq_input_start)-1)*100:+.2f}%)")
        
        # Make predictions
        spy_predictions = predictor.predict(spy_data, "SPY")
        qqq_predictions = predictor.predict(qqq_data, "QQQ")
        
        # Validate predictions are reasonable (within 2% of current price)
        spy_pred_close = spy_predictions['close'].iloc[-1]
        qqq_pred_close = qqq_predictions['close'].iloc[-1]
        
        spy_diff = abs((spy_pred_close - spy_input_end) / spy_input_end * 100)
        qqq_diff = abs((qqq_pred_close - qqq_input_end) / qqq_input_end * 100)
        
        if spy_diff > 5:
            st.warning(f"⚠️ SPY prediction seems off: {spy_diff:.1f}% from current - model may need retraining")
        if qqq_diff > 5:
            st.warning(f"⚠️ QQQ prediction seems off: {qqq_diff:.1f}% from current - model may need retraining")
            
    except Exception as e:
        st.warning(f"⚠️ Model error: {e}. Using trend-based prediction.")
        spy_predictions = create_fallback_prediction(spy_data)
        qqq_predictions = create_fallback_prediction(qqq_data)
    
    # Current prices
    spy_price = spy_data['close'].iloc[-1]
    qqq_price = qqq_data['close'].iloc[-1]
    
    # Calculate metrics
    spy_metrics = calculate_pred_metrics(spy_predictions, spy_price)
    qqq_metrics = calculate_pred_metrics(qqq_predictions, qqq_price)
    
    # Log predictions if enabled
    log_predictions = st.session_state.get('log_predictions', True)
    if log_predictions and spy_metrics and qqq_metrics:
        if 'last_pred_time' not in st.session_state or \
           (datetime.datetime.now() - st.session_state.last_pred_time).seconds >= 300:
            try:
                pred_logger.log_prediction("SPY", spy_price, spy_predictions,
                                          spy_metrics['direction'], spy_metrics['pct_change'], spy_metrics['target'])
                pred_logger.log_prediction("QQQ", qqq_price, qqq_predictions,
                                          qqq_metrics['direction'], qqq_metrics['pct_change'], qqq_metrics['target'])
                st.session_state.last_pred_time = datetime.datetime.now()
            except:
                pass
    
    # Top metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        delta = ((spy_data['close'].iloc[-1] / spy_data['close'].iloc[-2]) - 1) * 100
        st.metric("SPY Current", f"${spy_price:.2f}", f"{delta:+.2f}%")
    
    with col2:
        if spy_metrics:
            color = "🟢" if spy_metrics['direction'] == 'BULLISH' else "🔴" if spy_metrics['direction'] == 'BEARISH' else "🟡"
            # Show predicted price at T+20 based on actual model output
            pred_20_price = spy_predictions['close'].iloc[-1] if len(spy_predictions) > 0 else spy_metrics['target']
            st.metric(f"SPY Prediction {color}", f"${pred_20_price:.2f}", f"{spy_metrics['pct_change']:+.2f}%")
    
    with col3:
        delta = ((qqq_data['close'].iloc[-1] / qqq_data['close'].iloc[-2]) - 1) * 100
        st.metric("QQQ Current", f"${qqq_price:.2f}", f"{delta:+.2f}%")
    
    with col4:
        if qqq_metrics:
            color = "🟢" if qqq_metrics['direction'] == 'BULLISH' else "🔴" if qqq_metrics['direction'] == 'BEARISH' else "🟡"
            pred_20_price = qqq_predictions['close'].iloc[-1] if len(qqq_predictions) > 0 else qqq_metrics['target']
            st.metric(f"QQQ Prediction {color}", f"${pred_20_price:.2f}", f"{qqq_metrics['pct_change']:+.2f}%")
    
    # Show raw prediction data for verification
    with st.expander("🔬 Raw Prediction Details (Click to verify)"):
        st.write("**SPY Predicted Candles (T+1 to T+20):**")
        spy_pred_df = spy_predictions[['open', 'high', 'low', 'close']].copy()
        spy_pred_df.index = [f"T+{i+1}" for i in range(len(spy_pred_df))]
        st.dataframe(spy_pred_df.style.format("${:.2f}"), use_container_width=True)
        
        st.write("**QQQ Predicted Candles (T+1 to T+20):**")
        qqq_pred_df = qqq_predictions[['open', 'high', 'low', 'close']].copy()
        qqq_pred_df.index = [f"T+{i+1}" for i in range(len(qqq_pred_df))]
        st.dataframe(qqq_pred_df.style.format("${:.2f}"), use_container_width=True)
        
        st.caption("These predictions are generated by the Transformer model based on the last 20 candles of live data.")
    
    st.divider()
    
    # Charts Row 1: Current market
    st.subheader("📊 Current Market")
    col1, col2 = st.columns(2)
    
    with col1:
        fig = create_simple_candlestick(spy_data, "SPY - Current")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = create_simple_candlestick(qqq_data, "QQQ - Current")
        st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    
    # Charts Row 2: Predictions
    st.subheader("🔮 Predictions: Last 20 → Next 20 Candles")
    col1, col2 = st.columns(2)
    
    with col1:
        fig = create_prediction_candlestick(spy_data, spy_predictions, "SPY")
        st.plotly_chart(fig, use_container_width=True)
        
        if spy_metrics:
            st.info(f"**SPY Prediction:** {spy_metrics['direction']} ({spy_metrics['pct_change']:+.2f}%) → Target: ${spy_metrics['target']:.2f}")
    
    with col2:
        fig = create_prediction_candlestick(qqq_data, qqq_predictions, "QQQ")
        st.plotly_chart(fig, use_container_width=True)
        
        if qqq_metrics:
            st.info(f"**QQQ Prediction:** {qqq_metrics['direction']} ({qqq_metrics['pct_change']:+.2f}%) → Target: ${qqq_metrics['target']:.2f}")
    
    st.divider()
    
    # Validation Summary
    st.subheader("📊 Today's Prediction Accuracy")
    try:
        summary = pred_logger.get_daily_summary()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Predictions", summary.get('total_predictions', 0))
        with col2:
            st.metric("Validated", summary.get('validated', 0))
        with col3:
            acc = summary.get('direction_accuracy_pct', 0)
            st.metric("Direction Accuracy", f"{acc:.1f}%" if acc else "N/A")
        with col4:
            price_acc = summary.get('avg_price_accuracy_pct', 0)
            st.metric("Price Accuracy", f"{price_acc:.1f}%" if price_acc else "N/A")
        
        # Recent predictions table
        if summary.get('total_predictions', 0) > 0:
            with st.expander("📋 Recent Predictions Log"):
                show_predictions_table(pred_logger)
    except Exception as e:
        st.warning(f"Could not load prediction summary: {e}")


def calculate_pred_metrics(predictions: pd.DataFrame, current_price: float) -> dict:
    """Calculate prediction metrics"""
    if predictions is None or len(predictions) == 0:
        return {}
    
    pred_close = predictions['close'].iloc[-1]
    pct_change = ((pred_close - current_price) / current_price) * 100
    
    return {
        'direction': 'BULLISH' if pct_change > 0.05 else 'BEARISH' if pct_change < -0.05 else 'NEUTRAL',
        'pct_change': pct_change,
        'target': pred_close
    }


def create_fallback_prediction(df: pd.DataFrame) -> pd.DataFrame:
    """Create trend-based prediction when model isn't trained"""
    last_20 = df.tail(20)
    price_change = (last_20['close'].iloc[-1] - last_20['close'].iloc[0]) / last_20['close'].iloc[0]
    avg_candle_size = (last_20['high'] - last_20['low']).mean()
    
    last_close = last_20['close'].iloc[-1]
    last_time = df.index[-1]
    
    predictions = []
    current_price = last_close
    
    for i in range(5):
        trend_factor = price_change / 20
        noise = np.random.normal(0, avg_candle_size * 0.3)
        
        new_close = current_price * (1 + trend_factor) + noise
        new_open = current_price
        new_high = max(new_open, new_close) + abs(noise) * 0.5
        new_low = min(new_open, new_close) - abs(noise) * 0.5
        
        predictions.append({
            'open': new_open, 'high': new_high, 'low': new_low, 
            'close': new_close, 'volume': last_20['volume'].mean()
        })
        current_price = new_close
    
    future_times = [last_time + timedelta(minutes=i+1) for i in range(5)]
    return pd.DataFrame(predictions, index=future_times)


def validate_pending_predictions(pred_logger):
    """Validate pending predictions"""
    pending = pred_logger.get_pending_validations()
    
    if not pending:
        st.info("No pending validations")
        return
    
    validated = 0
    for record in pending:
        try:
            actual_data = get_live_data_for_prediction(record.symbol, bars=20)
            if len(actual_data) >= 5:
                pred_logger.validate_prediction(record.id, actual_data.tail(5))
                validated += 1
        except:
            pass
    
    if validated > 0:
        st.success(f"✅ Validated {validated} predictions")


def show_predictions_table(pred_logger):
    """Show recent predictions in a table"""
    import sqlite3
    
    try:
        conn = sqlite3.connect(pred_logger.db_path)
        df = pd.read_sql_query('''
            SELECT timestamp, symbol, current_price, predicted_direction, 
                   predicted_change_pct, predicted_target, direction_correct, 
                   price_accuracy_pct, validated
            FROM predictions ORDER BY timestamp DESC LIMIT 15
        ''', conn)
        conn.close()
        
        if len(df) > 0:
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%H:%M:%S')
            df['current_price'] = df['current_price'].apply(lambda x: f"${x:.2f}")
            df['predicted_target'] = df['predicted_target'].apply(lambda x: f"${x:.2f}")
            df['predicted_change_pct'] = df['predicted_change_pct'].apply(lambda x: f"{x:+.2f}%")
            df['direction_correct'] = df['direction_correct'].apply(lambda x: "✓" if x == 1 else "✗" if x == 0 else "⏳")
            df['price_accuracy_pct'] = df['price_accuracy_pct'].apply(lambda x: f"{x:.1f}%" if x else "⏳")
            df['validated'] = df['validated'].apply(lambda x: "✓" if x else "⏳")
            
            df.columns = ['Time', 'Symbol', 'Price', 'Direction', 'Pred%', 'Target', 'Dir✓', 'Acc', 'Valid']
            st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"Could not load predictions: {e}")


# Helper function to check if option is 0DTE
def is_0dte_option(symbol: str) -> bool:
    """Check if an option symbol is 0DTE (expires today)"""
    try:
        if len(symbol) < 15:
            return False
        
        # Find date part in symbol (format: SPY241203C00450000)
        # Date is YYMMDD starting after underlying
        for i in range(len(symbol)):
            if symbol[i].isdigit():
                date_str = symbol[i:i+6]  # YYMMDD
                if len(date_str) == 6:
                    year = 2000 + int(date_str[:2])
                    month = int(date_str[2:4])
                    day = int(date_str[4:6])
                    exp_date = date(year, month, day)
                    today = date.today()
                    return exp_date == today
        return False
    except:
        return False

# === LEFT SIDEBAR — CONFIGURATION ===
with st.sidebar:
    st.header("⚙️ Configuration")
    mode = st.selectbox("Mode", ["backtest", "live"])
    
    symbols = st.text_input("Symbols (comma-separated)", "SPY,QQQ")
    capital = st.number_input("Initial Capital ($)", value=1000.0, min_value=100.0, step=100.0)
    risk_pct = st.slider("Risk Per Trade (%)", 0.01, 5.0, 0.07, 0.01)

    st.markdown("### Backtest Options")
    use_csv = st.checkbox("Use CSV File")
    start_date = st.date_input("Start Date", datetime.date(2025, 11, 3))
    end_date = st.date_input("End Date", datetime.date(2025, 12, 1))
    monte_carlo = st.checkbox("Monte Carlo Simulation")

    if st.button("Run Backtest", type="primary"):
        st.session_state.run_backtest = True

    st.divider()
    
    # Prediction settings (only show if available)
    if PREDICTION_AVAILABLE:
        st.header("🔮 Prediction Settings")
        log_predictions = st.checkbox("📝 Log Predictions", value=True)
        
        if st.button("🔄 Retrain Model"):
            st.session_state.retrain_model = True
        
        if st.button("🔍 Validate Pending"):
            st.session_state.validate_pending = True

# === MAIN NAVIGATION TABS ===
st.markdown("<h1 style='text-align: center;'>🤖 Mike Agent - Unified Dashboard</h1>", unsafe_allow_html=True)

# Create tabs for navigation
tab_trading, tab_predictions = st.tabs(["📊 Trading Dashboard", "🔮 Price Predictions"])

# === MARKET STATUS BAR (FULL WIDTH) ===
def get_market_status():
    est = pytz.timezone('US/Eastern')
    now = datetime.datetime.now(est)
    
    # Market hours: 9:30 AM - 4:00 PM EST
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    # Calculate next trading day at 9:30 AM EST (market open time)
    def skip_weekends(date):
        while date.weekday() >= 5:  # Saturday=5, Sunday=6
            date += datetime.timedelta(days=1)
        return date
    
    if now.weekday() >= 5:  # Weekend
        if now.weekday() == 5:  # Saturday
            next_trading_day = now + datetime.timedelta(days=2)  # Monday
        else:  # Sunday
            next_trading_day = now + datetime.timedelta(days=1)  # Monday
        next_trading_day = skip_weekends(next_trading_day)
    elif now > market_close:  # After market close
        next_trading_day = now + datetime.timedelta(days=1)
        next_trading_day = skip_weekends(next_trading_day)
    elif now < market_open:  # Before market open
        next_trading_day = now  # Today
    else:  # During market hours
        next_trading_day = now + datetime.timedelta(days=1)
        next_trading_day = skip_weekends(next_trading_day)
    
    # Set to 9:30 AM EST
    next_market_open = next_trading_day.replace(hour=9, minute=30, second=0, microsecond=0)
    
    if next_market_open < now:
        next_market_open = next_market_open + datetime.timedelta(days=1)
        next_market_open = skip_weekends(next_market_open)
    
    is_trading = market_open <= now <= market_close and now.weekday() < 5
    status = "MARKET OPEN — HUNTING" if is_trading else "WAITING FOR MARKET"
    color = "#00ff00" if is_trading else "#ffaa00"
    
    current_time = now.strftime('%I:%M:%S %p EST')
    close_time = market_close.strftime('%I:%M %p EST')
    
    if is_trading:
        time_remaining = market_close - now
        h, rem = divmod(int(time_remaining.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        time_str = f"{h}h {m}m"
        status_line = f"Closes: {close_time} | Time: {current_time}"
    else:
        countdown = next_market_open - now
        if countdown.total_seconds() < 0:
            countdown = datetime.timedelta(0)
        h, rem = divmod(int(countdown.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        time_str = f"{h}h {m}m" if h or m else f"{s}s"
        status_line = f"Next: {next_market_open.strftime('%A %I:%M %p EST')} | Closes: {close_time} | Time: {current_time}"
    
    # Compact 2-inch status bar
    status_html = f"""
    <div style="padding:8px 15px; border-radius:8px; background:#111; border:2px solid {color}; margin:10px 0; display:flex; justify-content:space-between; align-items:center; height:50px;">
        <div style="display:flex; align-items:center; gap:15px;">
            <span style="color:{color}; font-weight:bold; font-size:16px;">● {status}</span>
            <span style="color:#00ff88; font-size:18px; font-weight:bold;">{time_str}</span>
        </div>
        <div style="color:#aaa; font-size:13px;">{status_line}</div>
    </div>
    """
    st.markdown(status_html, unsafe_allow_html=True)

# === PORTFOLIO VALUE BAR (ALPACA STYLE) ===
def get_portfolio_bar_data():
    """Get portfolio value, P&L, and today's trade stats"""
    # Check if API keys are configured (basic validation)
    if not config.ALPACA_KEY or config.ALPACA_KEY == 'YOUR_ALPACA_PAPER_KEY' or len(config.ALPACA_KEY) < 20:
        return {
            'portfolio_value': 100000.0,
            'daily_pnl_pct': 0.0,
            'daily_pnl_dollar': 0.0,
            'num_trades_today': 0,
            'today_pnl': 0.0,
            'realized_pnl': 0.0,
            'error': 'Alpaca API keys not configured. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY environment variables.'
        }
    
    try:
        api = tradeapi.REST(
            config.ALPACA_KEY,
            config.ALPACA_SECRET,
            config.ALPACA_BASE_URL,
            api_version='v2'
        )
        account = api.get_account()
        portfolio_value = float(account.equity)
        
        # Calculate daily P&L percentage
        if hasattr(account, 'last_equity') and account.last_equity:
            last_equity = float(account.last_equity)
        else:
            try:
                last_equity = config.FORCE_CAPITAL if hasattr(config, 'FORCE_CAPITAL') else portfolio_value
            except:
                last_equity = portfolio_value
        
        daily_pnl_pct = ((portfolio_value - last_equity) / last_equity * 100) if last_equity > 0 else 0.0
        daily_pnl_dollar = portfolio_value - last_equity
        
        # Get today's trades directly from Alpaca using FIFO matching (same as report)
        est = pytz.timezone('US/Eastern')
        today = datetime.datetime.now(est).date()
        num_trades_today = 0  # Count completed trades (matched buy/sell pairs)
        realized_pnl = 0.0    # Realized P&L from completed trades only
        unrealized_pnl = 0.0  # Unrealized P&L from open positions
        
        try:
            # Get filled orders from today
            all_orders = api.list_orders(status='filled', limit=500, nested=True)
            
            # Filter for today's 0DTE option orders
            today_orders = []
            for order in all_orders:
                symbol = order.symbol
                
                # Only process 0DTE option orders
                if not is_0dte_option(symbol):
                    continue
                
                # Parse order date
                try:
                    if order.filled_at:
                        if isinstance(order.filled_at, str):
                            filled_dt = datetime.datetime.fromisoformat(order.filled_at.replace('Z', '+00:00')).astimezone(est)
                        else:
                            if hasattr(order.filled_at, 'astimezone'):
                                filled_dt = order.filled_at.astimezone(est)
                            else:
                                filled_dt = datetime.datetime.fromtimestamp(order.filled_at).astimezone(est)
                        order_date = filled_dt.date()
                    else:
                        continue
                    
                    # Only process today's orders
                    if order_date == today:
                        today_orders.append(order)
                except Exception as e:
                    continue
            
            # Separate buy and sell orders with individual order details
            buy_orders = {}
            sell_orders = {}
            
            for order in today_orders:
                symbol = order.symbol
                side = order.side.lower()
                filled_qty = float(order.filled_qty)
                filled_avg_price = float(order.filled_avg_price)
                
                # Get filled time
                if isinstance(order.filled_at, str):
                    filled_at = datetime.datetime.fromisoformat(order.filled_at.replace('Z', '+00:00')).astimezone(est)
                else:
                    if hasattr(order.filled_at, 'astimezone'):
                        filled_at = order.filled_at.astimezone(est)
                    else:
                        filled_at = datetime.datetime.fromtimestamp(order.filled_at).astimezone(est)
                
                if side == 'buy':
                    if symbol not in buy_orders:
                        buy_orders[symbol] = []
                    buy_orders[symbol].append({
                        'qty': filled_qty,
                        'price': filled_avg_price,
                        'time': filled_at
                    })
                else:  # sell
                    if symbol not in sell_orders:
                        sell_orders[symbol] = []
                    sell_orders[symbol].append({
                        'qty': filled_qty,
                        'price': filled_avg_price,
                        'time': filled_at
                    })
            
            # Match buy/sell pairs using FIFO (same as report)
            all_symbols = set(list(buy_orders.keys()) + list(sell_orders.keys()))
            
            for symbol in all_symbols:
                buys = sorted(buy_orders.get(symbol, []), key=lambda x: x['time'])
                sells = sorted(sell_orders.get(symbol, []), key=lambda x: x['time'])
                
                buy_index = 0
                sell_index = 0
                
                while buy_index < len(buys) or sell_index < len(sells):
                    if buy_index < len(buys) and (sell_index >= len(sells) or buys[buy_index]['time'] <= sells[sell_index]['time']):
                        # Process buy
                        buy = buys[buy_index]
                        buy_index += 1
                        remaining_qty = buy['qty']
                        
                        # Match with sells (FIFO)
                        while remaining_qty > 0.01 and sell_index < len(sells):
                            sell = sells[sell_index]
                            sell_qty = min(remaining_qty, sell['qty'])
                            
                            # Calculate P&L for this completed trade
                            entry_cost = buy['price'] * sell_qty * 100
                            exit_proceeds = sell['price'] * sell_qty * 100
                            pnl = exit_proceeds - entry_cost
                            
                            realized_pnl += pnl
                            num_trades_today += 1  # Count each completed trade
                            
                            # Update remaining quantities
                            remaining_qty -= sell_qty
                            if sell['qty'] - sell_qty < 0.01:
                                sell_index += 1
                            else:
                                sells[sell_index]['qty'] -= sell_qty
            
            # Calculate unrealized P&L from open positions (all positions, not just opened today)
            try:
                positions = api.list_positions()
                for pos in positions:
                    symbol = pos.symbol
                    if not is_0dte_option(symbol):
                        continue
                    
                    qty = float(pos.qty)
                    avg_entry = float(pos.avg_entry_price) if hasattr(pos, 'avg_entry_price') and pos.avg_entry_price else 0.0
                    current_value = float(pos.market_value) if hasattr(pos, 'market_value') and pos.market_value else 0.0
                    
                    if avg_entry > 0 and qty > 0:
                        cost_basis = qty * avg_entry * 100
                        unrealized_pnl += (current_value - cost_basis)
            except Exception as e:
                pass
            
            # Fallback to database if Alpaca doesn't have data
            if num_trades_today == 0 and realized_pnl == 0.0:
                if TRADE_DB_AVAILABLE:
                    try:
                        trade_db = TradeDatabase()
                        all_trades = trade_db.get_all_trades()
                        
                        today_trades = []
                        today_pnl = 0.0  # Initialize today_pnl
                        for trade in all_trades:
                            try:
                                trade_timestamp = trade.get('timestamp', '')
                                if not trade_timestamp:
                                    continue
                                
                                if ' ' in trade_timestamp:
                                    trade_date_str = trade_timestamp.split(' ')[0]
                                    trade_date = datetime.datetime.strptime(trade_date_str, '%Y-%m-%d').date()
                                else:
                                    trade_date = datetime.datetime.strptime(trade_timestamp, '%Y-%m-%d').date()
                                
                                if trade_date == today:
                                    today_trades.append(trade)
                                    if trade.get('action') == 'SELL' and trade.get('pnl') is not None:
                                        try:
                                            pnl_value = float(trade['pnl']) if trade['pnl'] != '' else 0.0
                                            if pnl_value != 0.0:
                                                today_pnl += pnl_value
                                        except (ValueError, TypeError):
                                            pass
                            except Exception:
                                continue
                        
                        # Fallback uses old counting method - set defaults
                        num_trades_today = len([t for t in today_trades if t.get('action') == 'BUY'])
                        if realized_pnl == 0.0:
                            realized_pnl = today_pnl
                    except Exception:
                        pass
        
        except Exception as e:
            # If Alpaca fails, initialize defaults
            num_trades_today = 0
            realized_pnl = 0.0
            unrealized_pnl = 0.0
        
        # Return realized P&L separately from unrealized (matching report methodology)
        return {
            'portfolio_value': portfolio_value,
            'daily_pnl_pct': daily_pnl_pct,
            'daily_pnl_dollar': daily_pnl_dollar,
            'num_trades_today': num_trades_today,  # Completed trades (matched pairs)
            'realized_pnl': realized_pnl,          # Realized P&L from completed trades
            'unrealized_pnl': unrealized_pnl,      # Unrealized P&L from open positions
            'today_pnl': realized_pnl  # Show realized P&L (same as report)
        }
    except Exception as e:
        error_msg = str(e)
        # Check if it's an API key/authentication error
        if 'Key ID' in error_msg or 'API key' in error_msg or 'APCA_API_KEY_ID' in error_msg or 'authentication' in error_msg.lower() or 'unauthorized' in error_msg.lower():
            return {
                'portfolio_value': 100000.0,
                'daily_pnl_pct': 0.0,
                'daily_pnl_dollar': 0.0,
                'num_trades_today': 0,
                'today_pnl': 0.0,
                'realized_pnl': 0.0,
                'error': f"Alpaca API key error: {error_msg}. Please set APCA_API_KEY_ID and APCA_API_SECRET_KEY environment variables."
            }
        # Other errors (network, timeout, etc.) - return default values without error message
        # This allows dashboard to show default values when API is temporarily unavailable
        return {
            'portfolio_value': 100000.0,
            'daily_pnl_pct': 0.0,
            'daily_pnl_dollar': 0.0,
            'num_trades_today': 0,
            'today_pnl': 0.0,
            'realized_pnl': 0.0
        }

def display_portfolio_bar(portfolio_data):
    """Display the portfolio bar"""
    # Show error if API key issue
    if 'error' in portfolio_data:
        st.error(portfolio_data['error'])
        st.info("💡 **To fix:** Set these environment variables on Railway/local:\n- `APCA_API_KEY_ID`\n- `APCA_API_SECRET_KEY`\n- `APCA_API_BASE_URL` (optional, defaults to paper trading)")
        return

    # Portfolio bar in Alpaca style
    pnl_color = "#ef4444" if portfolio_data['daily_pnl_pct'] < 0 else "#10b981"
    realized_pnl = portfolio_data.get('realized_pnl', portfolio_data.get('today_pnl', 0))

    portfolio_bar_html = f"""
    <div style="background:white; padding:20px; border-radius:8px; margin:15px 0; box-shadow:0 1px 3px rgba(0,0,0,0.1); display:flex; justify-content:space-between; align-items:center;">
        <div style="flex:1;">
            <div style="color:#6b7280; font-size:14px; margin-bottom:5px;">Your portfolio</div>
            <div style="display:flex; align-items:baseline; gap:10px;">
                <span style="color:#9ca3af; font-size:20px;">$</span>
                <span style="color:#111827; font-size:32px; font-weight:bold;">{portfolio_data['portfolio_value']:,.2f}</span>
                <span style="color:{pnl_color}; font-size:20px; font-weight:bold;">{portfolio_data['daily_pnl_pct']:+.2f}%</span>
            </div>
            <div style="color:#9ca3af; font-size:12px; margin-top:5px;">{datetime.datetime.now(pytz.timezone('US/Eastern')).strftime('%B %d, %I:%M %p %Z')}</div>
        </div>
        <div style="flex:1; display:flex; gap:30px; justify-content:center;">
            <div style="text-align:center;">
                <div style="color:#6b7280; font-size:12px; margin-bottom:5px;">Completed Trades</div>
                <div style="color:#111827; font-size:24px; font-weight:bold;">{portfolio_data['num_trades_today']}</div>
            </div>
            <div style="text-align:center;">
                <div style="color:#6b7280; font-size:12px; margin-bottom:5px;">Today's P&L</div>
                <div style="color:{pnl_color}; font-size:24px; font-weight:bold;">${realized_pnl:+,.2f}</div>
            </div>
        </div>
    </div>
    """
    st.markdown(portfolio_bar_html, unsafe_allow_html=True)


def display_current_positions():
    """Display current positions"""
    st.markdown("### Current Positions")
    positions_df = get_alpaca_positions()

    if not positions_df.empty:
        st.dataframe(
            positions_df,
            width='stretch',
            hide_index=True,
            height=200
        )
        
        col1, col2, col3, col4 = st.columns(4)
        total_market_value = sum([float(v.replace('$', '').replace(',', '')) for v in positions_df['Market Value']])
        total_cost_basis = sum([float(v.replace('$', '').replace(',', '')) for v in positions_df['Cost Basis']])
        total_pnl = total_market_value - total_cost_basis
        total_pnl_pct = (total_pnl / total_cost_basis * 100) if total_cost_basis > 0 else 0.0
        
        with col1:
            st.metric("Total Positions", len(positions_df))
        with col2:
            st.metric("Market Value", f"${total_market_value:,.2f}")
        with col3:
            st.metric("Total P&L", f"${total_pnl:+,.2f}", f"{total_pnl_pct:+.2f}%")
        with col4:
            st.metric("Cost Basis", f"${total_cost_basis:,.2f}")
    else:
        st.info("No open positions - waiting for trades")


def display_trade_statistics(portfolio_data):
    """Display trade statistics"""
    try:
        if TRADE_DB_AVAILABLE:
            try:
                trade_db = TradeDatabase()
                stats = trade_db.get_trade_statistics(filter_0dte=True)
                total_trades_count = stats.get('total_trades', 0)
                pnl_summary = stats
            except Exception as db_error:
                st.warning(f"Database error loading statistics: {db_error}")
                total_trades_count = 0
                pnl_summary = {'total_trades': 0, 'win_rate': 0.0, 'total_pnl': 0.0}
        else:
            try:
                from mike_agent_trades import MikeAgentTradeDB
                trade_db_local = MikeAgentTradeDB()
                pnl_summary = trade_db_local.get_total_pnl()
                total_trades_count = pnl_summary.get('total_trades', 0)
            except:
                total_trades_count = 0
                pnl_summary = {'total_trades': 0, 'win_rate': 0.0, 'total_pnl': 0.0}
    except Exception as e:
        st.warning(f"Error loading trade statistics: {e}")
        total_trades_count = 0
        pnl_summary = {'total_trades': 0, 'win_rate': 0.0, 'total_pnl': 0.0}

    st.markdown("### Trade Statistics (0DTE Only)")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Trades", total_trades_count)
    with col2:
        try:
            win_rate = pnl_summary.get('win_rate', 0.0)
            st.metric("Win Rate", f"{win_rate:.1f}%")
        except Exception:
            st.metric("Win Rate", "0.0%")
    with col3:
        try:
            total_pnl = pnl_summary.get('total_pnl', 0.0)
            st.metric("Total P&L", f"${total_pnl:+,.2f}")
        except Exception:
            st.metric("Total P&L", "$0.00")


def display_trading_history():
    """Display trading history table"""
    st.markdown("### Trading History")
    history_df = get_trading_history_alpaca_style()

    if not history_df.empty:
        st.dataframe(
            history_df,
            width='stretch',
            hide_index=True,
            height=300
        )
    else:
        st.info("No trades yet — waiting for first trade")


def display_activity_log():
    """Display activity log"""
    st.markdown("### Real-Time Activity Log")
    try:
        log_text = get_activity_log()
    except Exception as e:
        log_text = f"Reading log... Error: {e}"

    st.text_area(
        "Activity Log (Latest on Top)",
        log_text,
        height=400,
        key="activity_log",
        label_visibility="collapsed"
    )


def display_market_snapshot():
    """Display market snapshot placeholder"""
    pass


def display_ensemble_status():
    """Display ensemble status placeholder"""
    pass


def display_account_summary():
    """Display account summary placeholder"""
    pass


def display_backtest_results():
    """Display backtest results if running"""
    symbols = st.session_state.get('symbols_input', 'SPY,QQQ')
    capital = st.session_state.get('capital_input', 1000.0)
    risk_pct = st.session_state.get('risk_pct_input', 0.07)
    start_date = st.session_state.get('start_date_input', datetime.date(2025, 11, 3))
    end_date = st.session_state.get('end_date_input', datetime.date(2025, 12, 1))

# === BACKTEST RESULTS (if running) ===
if st.session_state.get('run_backtest', False):
    with st.spinner("Running backtest... This may take a few moments."):
        try:
            symbol_list = [s.strip() for s in symbols.split(',')]
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            
            results = []
            total_pnl = 0.0
            total_trades = 0
            
            for symbol in symbol_list:
                try:
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(start=start_str, end=end_str, interval='1d')
                    
                    if isinstance(hist.columns, pd.MultiIndex):
                        hist.columns = hist.columns.get_level_values(0)
                    
                    if len(hist) > 0:
                        initial_price = hist['Close'].iloc[0]
                        final_price = hist['Close'].iloc[-1]
                        price_change_pct = ((final_price - initial_price) / initial_price) * 100
                        
                        simulated_trades = max(1, len(hist) // 5)
                        avg_trade_pnl = (price_change_pct * capital * risk_pct) / simulated_trades
                        symbol_pnl = avg_trade_pnl * simulated_trades
                        
                        results.append({
                            'Symbol': symbol,
                            'Trades': simulated_trades,
                            'P&L': symbol_pnl,
                            'Return %': price_change_pct
                        })
                        total_pnl += symbol_pnl
                        total_trades += simulated_trades
                except Exception as e:
                    st.error(f"Error backtesting {symbol}: {e}")
            
            if results:
                st.success("✅ Backtest Complete!")
                df_results = pd.DataFrame(results)
                st.dataframe(df_results, width='stretch', hide_index=True)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Trades", total_trades)
                with col2:
                    st.metric("Total P&L", f"${total_pnl:+,.2f}")
                with col3:
                    return_pct = (total_pnl / capital) * 100
                    st.metric("Total Return", f"{return_pct:+.2f}%")
                
                st.session_state.backtest_results = {
                    'total_trades': total_trades,
                    'total_pnl': total_pnl,
                    'return_pct': return_pct
                }
            
            st.session_state.run_backtest = False
        except Exception as e:
            st.error(f"Backtest error: {e}")
            st.session_state.run_backtest = False

# === CURRENT POSITIONS TABLE (ALPACA) ===
def get_alpaca_positions():
    """Fetch current positions from Alpaca API"""
    # Check if API keys are configured (basic validation)
    if not config.ALPACA_KEY or config.ALPACA_KEY == 'YOUR_ALPACA_PAPER_KEY' or len(config.ALPACA_KEY) < 20:
        return pd.DataFrame()
    
    try:
        api = tradeapi.REST(
            config.ALPACA_KEY,
            config.ALPACA_SECRET,
            config.ALPACA_BASE_URL,
            api_version='v2'
        )
        
        positions = api.list_positions()
        # Filter for option positions AND 0DTE only
        option_positions = [pos for pos in positions if pos.asset_class == 'us_option' or ('C' in pos.symbol or 'P' in pos.symbol)]
        # Filter to show ONLY 0DTE trades
        odte_positions = [pos for pos in option_positions if is_0dte_option(pos.symbol)]
        
        if not odte_positions:
            return pd.DataFrame()
        
        option_positions = odte_positions  # Use filtered list
        
        positions_data = []
        for pos in option_positions:
            qty = float(pos.qty)
            market_value = float(pos.market_value)
            
            # Correct price calculation: market_value / (qty * 100) for options
            current_price = market_value / (qty * 100) if qty > 0 else 0.0
            
            avg_entry = float(pos.avg_entry_price) if hasattr(pos, 'avg_entry_price') and pos.avg_entry_price else current_price
            cost_basis = avg_entry * qty * 100
            
            total_pnl = market_value - cost_basis
            total_pnl_pct = (total_pnl / cost_basis * 100) if cost_basis > 0 else 0.0
            today_pnl = total_pnl  # Simplified
            today_pnl_pct = total_pnl_pct
            
            positions_data.append({
                'Asset': pos.symbol,
                'Price': f"${current_price:.2f}",
                'Qty': int(qty),
                'Side': 'Long' if qty > 0 else 'Short',
                'Market Value': f"${market_value:,.2f}",
                'Avg Entry': f"${avg_entry:.4f}",
                'Cost Basis': f"${cost_basis:,.2f}",
                "Today's P/L (%)": f"{today_pnl_pct:+.2f}%",
                "Today's P/L ($)": f"${today_pnl:+,.2f}",
                'Total P/L (%)': f"{total_pnl_pct:+.2f}%"
            })
        
        return pd.DataFrame(positions_data)
    except Exception as e:
        error_msg = str(e)
        # Don't show error in UI if it's just API key issue (already shown in portfolio section)
        if 'Key ID' not in error_msg and 'API key' not in error_msg and 'APCA_API_KEY_ID' not in error_msg:
            st.error(f"Error fetching Alpaca positions: {e}")
        return pd.DataFrame()

# === TRADING HISTORY TABLE (ALPACA POSITIONS STYLE) - RIGHT ABOVE LOG ===

def get_trading_history_alpaca_style():
    """Get trading history directly from Alpaca orders (most accurate fill prices)
    
    This ensures both local and Railway/mobile show the same data by using Alpaca API
    as the single source of truth. Database is only used as fallback.
    """
    try:
        # Fetch orders directly from Alpaca for accurate fill prices
        # This ensures both local and Railway show the same data
        api = tradeapi.REST(
            config.ALPACA_KEY,
            config.ALPACA_SECRET,
            config.ALPACA_BASE_URL,
            api_version='v2'
        )
        
        # Get filled orders from Alpaca (increased limit to get all historical trades)
        try:
            orders = api.list_orders(status='filled', limit=500, nested=False)
        except Exception as e:
            st.warning(f"Could not fetch orders from Alpaca: {e}, using database fallback")
            orders = []
        
        # Filter for option orders AND 0DTE only (NO DATE FILTER - keep all trades)
        option_orders = []
        for order in orders:
            symbol = order.symbol
            # Check for option pattern
            if len(symbol) >= 10 and (('C' in symbol[-9:] and symbol[-9:][-1].isdigit()) or 
                                      ('P' in symbol[-9:] and symbol[-9:][-1].isdigit()) or
                                      symbol.startswith('SPY') or symbol.startswith('QQQ') or symbol.startswith('SPX')):
                # Only include 0DTE trades (but keep ALL dates, not just today)
                if is_0dte_option(symbol):
                    option_orders.append(order)
        
        # If we have Alpaca orders, use them
        if option_orders:
            # Sort by filled_at (newest first) - show all trades, not just 20
            try:
                option_orders.sort(key=lambda x: x.filled_at if x.filled_at else x.submitted_at, reverse=True)
            except:
                pass
            recent_orders = option_orders  # Show all trades, not limited to 20
            
            # Format in Alpaca positions table style
            display_data = []
            for order in recent_orders:
                # Format timestamps separately for Submitted At and Filled At
                submitted_time = "N/A"
                filled_time = "N/A"
                
                try:
                    # Parse Submitted At timestamp
                    if order.submitted_at:
                        submitted_dt = datetime.datetime.fromisoformat(order.submitted_at.replace('Z', '+00:00'))
                        submitted_dt = submitted_dt.astimezone(pytz.timezone('US/Eastern'))
                        submitted_time = submitted_dt.strftime('%b %d, %Y %I:%M:%S %p')
                except:
                    submitted_time = "N/A"
                
                try:
                    # Parse Filled At timestamp
                    if order.filled_at:
                        filled_dt = datetime.datetime.fromisoformat(order.filled_at.replace('Z', '+00:00'))
                        filled_dt = filled_dt.astimezone(pytz.timezone('US/Eastern'))
                        filled_time = filled_dt.strftime('%b %d, %Y %I:%M:%S %p')
                except:
                    filled_time = "N/A"
                
                # Get fill price from Alpaca (most accurate)
                fill_price = float(order.filled_avg_price) if hasattr(order, 'filled_avg_price') and order.filled_avg_price else 0.0
                
                display_data.append({
                    'Asset': order.symbol,
                    'Order Type': order.type.capitalize() if hasattr(order, 'type') else 'Market',
                    'Side': order.side.lower(),
                    'Qty': f"{float(order.qty):.2f}",
                    'Filled Qty': f"{float(order.filled_qty):.2f}" if hasattr(order, 'filled_qty') and order.filled_qty else f"{float(order.qty):.2f}",
                    'Avg. Fill Price': f"{fill_price:.2f}" if fill_price > 0 else "N/A",
                    'Status': order.status if hasattr(order, 'status') else 'filled',
                    'Source': order.source if hasattr(order, 'source') else 'access_key',
                    'Submitted At': submitted_time,
                    'Filled At': filled_time
                })
            
            return pd.DataFrame(display_data)
    
    except Exception as e:
        st.warning(f"Error loading trading history from Alpaca: {e}, using database fallback")
    
    # Fallback to database if Alpaca fails or no orders found
    try:
        if TRADE_DB_AVAILABLE:
            try:
                trade_db = TradeDatabase()
                # Get ONLY 0DTE trades from database
                all_trades = trade_db.get_0dte_trades_only()
            except Exception as db_error:
                st.warning(f"Database error: {db_error}, trying legacy fallback")
                all_trades = []
        else:
            # Legacy fallback
            try:
                from mike_agent_trades import MikeAgentTradeDB
                trade_db = MikeAgentTradeDB()
                all_trades = trade_db.get_all_trades()
                # Filter for 0DTE manually
                all_trades = [t for t in all_trades if is_0dte_option(t.get('symbol', ''))]
            except:
                all_trades = []
        
        if not all_trades:
            return pd.DataFrame()
        
        # Show all trades, not just last 20 (NO DATE FILTER - keep all trades)
        recent_trades = all_trades[:]  # Show all trades
        recent_trades.reverse()
        
        display_data = []
        for trade in recent_trades:
            # Get submitted_at and filled_at from database
            submitted_time = trade.get('submitted_at', '')
            filled_time = trade.get('filled_at', '')
            
            # If not in database, fall back to timestamp
            if not submitted_time:
                timestamp = trade.get('timestamp', '')
                try:
                    dt = datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                    submitted_time = dt.strftime('%b %d, %Y %I:%M:%S %p')
                except:
                    submitted_time = timestamp if timestamp else "N/A"
            
            if not filled_time:
                filled_time = submitted_time  # Use submitted time as fallback
            
            # Format timestamps if they're in ISO format
            try:
                if submitted_time and 'T' in submitted_time:
                    submitted_dt = datetime.datetime.fromisoformat(submitted_time.replace('Z', '+00:00'))
                    submitted_dt = submitted_dt.astimezone(pytz.timezone('US/Eastern'))
                    submitted_time = submitted_dt.strftime('%b %d, %Y %I:%M:%S %p')
            except:
                pass
            
            try:
                if filled_time and 'T' in filled_time:
                    filled_dt = datetime.datetime.fromisoformat(filled_time.replace('Z', '+00:00'))
                    filled_dt = filled_dt.astimezone(pytz.timezone('US/Eastern'))
                    filled_time = filled_dt.strftime('%b %d, %Y %I:%M:%S %p')
            except:
                pass
            
            # Use premium price instead of strike price
            if trade['action'] == 'BUY':
                fill_price = trade.get('entry_premium', 0.0)
                if fill_price == 0.0 or fill_price == '':
                    price_val = float(trade.get('price', 0.0))
                    fill_price = price_val if price_val < 50.0 else 0.0
            else:  # SELL
                fill_price = trade.get('exit_premium', 0.0)
                if fill_price == 0.0 or fill_price == '':
                    price_val = float(trade.get('price', 0.0))
                    if price_val > 0 and price_val < 50.0:
                        fill_price = price_val
                    else:
                        fill_price = 0.0
            
            try:
                fill_price = float(fill_price) if fill_price != '' and fill_price != 0.0 else 0.0
            except (ValueError, TypeError):
                fill_price = 0.0
            
            display_data.append({
                'Asset': trade['symbol'],
                'Order Type': 'Market',
                'Side': trade['action'].lower(),
                'Qty': f"{int(trade['qty']):.2f}",
                'Filled Qty': f"{int(trade['qty']):.2f}",
                'Avg. Fill Price': f"{fill_price:.2f}" if fill_price > 0 else "N/A",
                'Status': 'filled',
                'Source': 'access_key',
                'Submitted At': submitted_time if submitted_time else "N/A",
                'Filled At': filled_time if filled_time else "N/A"
            })
        
        return pd.DataFrame(display_data)
    except Exception as e:
        st.error(f"Error loading trading history from database: {e}")
        return pd.DataFrame()

# === REAL-TIME ACTIVITY LOG ===

def get_activity_log():
    """
    Get activity log from multiple sources.
    Prioritizes Alpaca account activities for consistency across local/Railway.
    Falls back to local log files if available.
    """
    log_entries = []
    
    # Try to get activities from Alpaca API (synced across all deployments)
    try:
        api = tradeapi.REST(
            config.ALPACA_KEY,
            config.ALPACA_SECRET,
            config.ALPACA_BASE_URL,
            api_version='v2'
        )
        
        # Get recent account activities (orders, fills, etc.)
        # This ensures both local and Railway show the same data
        try:
            activities = api.get_account_activities(activity_type='FILL', limit=50)
            for activity in activities:
                timestamp = activity.transaction_time if hasattr(activity, 'transaction_time') else activity.date
                symbol = activity.symbol if hasattr(activity, 'symbol') else 'N/A'
                qty = activity.qty if hasattr(activity, 'qty') else 0
                price = activity.price if hasattr(activity, 'price') else 0.0
                
                log_entries.append(f"[{timestamp}] 📊 FILL: {symbol} | Qty: {qty} @ ${price:.2f}")
        except Exception as e:
            # Alpaca activity feed might not be available, that's okay
            pass
    except Exception as e:
        # Alpaca API might not be available, continue to local logs
        pass
    
    # Also try to read from local log files (if running locally)
    try:
        today = datetime.datetime.now().strftime('%Y%m%d')
        log_file = f"logs/mike_agent_safe_{today}.log"
        
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                lines = f.readlines()
                # Add to log entries (already in correct format)
                log_entries.extend([line.strip() for line in lines[-50:]])  # Last 50 lines
        elif os.path.exists("mike.log"):
            with open("mike.log", "r") as f:
                lines = f.readlines()
                log_entries.extend([line.strip() for line in lines[-50:]])
        else:
            if os.path.exists("logs"):
                log_files = [f for f in os.listdir("logs") if f.startswith("mike_agent_safe_") and f.endswith(".log")]
                if log_files:
                    latest_log = sorted(log_files)[-1]
                    with open(f"logs/{latest_log}", "r") as f:
                        lines = f.readlines()
                        log_entries.extend([line.strip() for line in lines[-50:]])
    except Exception as e:
        pass
    
    # Combine and format
    if log_entries:
        # Reverse order: latest on top
        log_entries.reverse()
        log_text = "\n".join(log_entries[:100])  # Last 100 entries
    else:
        log_text = "Agent running in background...\nWaiting for activity..."
    
    return log_text


# ============================================================================
# TAB 1: TRADING DASHBOARD (Render Function)  
# ============================================================================
def render_trading_tab():
    """Render the trading dashboard tab"""
    st.markdown("<h2 style='text-align: center; margin-top: -10px;'>Live Agent Brain Activity</h2>", unsafe_allow_html=True)

    # Auto-refresh indicator
    if not st.session_state.get('run_backtest', False):
        est = pytz.timezone('US/Eastern')
        now = datetime.datetime.now(est)
        refresh_time = now.strftime("%I:%M:%S %p EST")
        st.caption(f"🔄 Auto-refreshing every 10 seconds | Last updated: {refresh_time}")
    
    # Market status bar
    get_market_status()
    
    # Portfolio bar
    portfolio_data = get_portfolio_bar_data()
    display_portfolio_bar(portfolio_data)
    
    # Current positions
    display_current_positions()
    
    # Trade statistics
    display_trade_statistics(portfolio_data)
    
    # Trading history table
    display_trading_history()
    
    # Activity log
    display_activity_log()


# ============================================================================
# MAIN EXECUTION - TABS
# ============================================================================
with tab_trading:
    render_trading_tab()

# ============================================================================
# TAB 2: PRICE PREDICTIONS
# ============================================================================
with tab_predictions:
    if not PREDICTION_AVAILABLE:
        st.error("⚠️ Prediction module not available. Please check price_predictor.py and prediction_logger.py")
    else:
        render_prediction_tab()

# Auto-refresh every 10 seconds - only if not running backtest
if not st.session_state.get('run_backtest', False):
    time.sleep(10)
    st.rerun()
