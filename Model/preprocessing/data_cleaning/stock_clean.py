import pandas as pd
import glob
import os
import numpy as np
import pandas_ta as ta
import torch
from sklearn.preprocessing import StandardScaler

def create_data():
    start_date = '2014-01-01'
    end_date = '2016-03-31'
    output_file = "data/combined_stock_data.jsonl"
    path = "/home/matt/Git/Chirp-Alpha/data/stock_data"

    all_files = glob.glob(os.path.join(path, "*.csv"))

    with open(output_file, "w") as f:
        for filename in all_files:
            ticker = os.path.splitext(os.path.basename(filename))[0]
            try:
                df = pd.read_csv(filename)
                date_col = 'Date' if 'Date' in df.columns else 'date'
                df[date_col] = pd.to_datetime(df[date_col])
                mask = (df[date_col] >= start_date) & (df[date_col] <= end_date)
                df_filtered = df.loc[mask].copy()
                if not df_filtered.empty:
                    df_filtered['ticker'] = ticker
                    df_filtered[date_col] = df_filtered[date_col].dt.strftime('%Y-%m-%d')
                    json_data = df_filtered.to_json(orient='records', lines=True)
                    f.write(json_data + "\n")
            except Exception as e:
                print(f"Error processing {filename}: {e}")

def create_features():
    input_file = f"{DATA_DIR}/combined_stock_data.jsonl"
    if not os.path.exists(input_file):
        print(f"Combined stock data not found: {input_file}. Run create_data() first.")
        return None
    output_file = f"{DATA_DIR}/stock_data.jsonl"
    
    df = pd.read_json(input_file, lines=True)
    # Rename columns properly
    rename_cols = {}
    for c in df.columns:
        lower = c.lower()
        if lower in ['open', 'high', 'low', 'close', 'volume', 'date']:
            rename_cols[c] = lower.capitalize()
    df = df.rename(columns=rename_cols)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values(by=['ticker', 'Date'])
    feature_dfs = []
    for ticker, group in df.groupby('ticker'):
        g = group.copy().sort_values('Date')
        g['return_1d'] = g['Close'].pct_change(1)
        g['return_5d'] = g['Close'].pct_change(5)
        g['return_10d'] = g['Close'].pct_change(10)
        g['return_20d'] = g['Close'].pct_change(20)
        g['log_return_1d'] = np.log(g['Close'] / g['Close'].shift(1))
        g['gap'] = g['Open'] - g['Close'].shift(1)
        g['intraday_return'] = (g['Close'] - g['Open']) / (g['Open'] + 1e-9)
        g['SMA_5'] = ta.sma(g['Close'], length=5)
        g['SMA_10'] = ta.sma(g['Close'], length=10)
        g['SMA_20'] = ta.sma(g['Close'], length=20)
        g['SMA_50'] = ta.sma(g['Close'], length=50)
        g['EMA_12'] = ta.ema(g['Close'], length=12)
        g['EMA_26'] = ta.ema(g['Close'], length=26)
        g['price_to_SMA5'] = g['Close'] / (g['SMA_5'] + 1e-9)
        g['price_to_SMA20'] = g['Close'] / (g['SMA_20'] + 1e-9)
        g['volatility_5d'] = g['return_1d'].rolling(5).std()
        g['volatility_20d'] = g['return_1d'].rolling(20).std()
        g['ATR_14'] = ta.atr(g['High'], g['Low'], g['Close'], length=14)
        bbands = ta.bbands(g['Close'], length=20, std=2)
        if bbands is not None and not bbands.empty:
            bb_cols = bbands.columns.tolist()
            bb_upper = [c for c in bb_cols if 'BBU' in c][0] if any('BBU' in c for c in bb_cols) else None
            bb_middle = [c for c in bb_cols if 'BBM' in c][0] if any('BBM' in c for c in bb_cols) else None
            bb_lower = [c for c in bb_cols if 'BBL' in c][0] if any('BBL' in c for c in bb_cols) else None
            if bb_upper and bb_middle and bb_lower:
                g['BB_width'] = (bbands[bb_upper] - bbands[bb_lower]) / (bbands[bb_middle] + 1e-9)
                band_range = bbands[bb_upper] - bbands[bb_lower]
                g['BB_position'] = np.where(band_range > 1e-9, (g['Close'] - bbands[bb_lower]) / band_range, 0.5)
        g['RSI_14'] = ta.rsi(g['Close'], length=14)
        macd = ta.macd(g['Close'])
        if macd is not None and not macd.empty:
            macd_cols = macd.columns.tolist()
            macd_line = [c for c in macd_cols if 'MACD_' in c and 'MACDs' not in c and 'MACDh' not in c]
            macd_signal = [c for c in macd_cols if 'MACDs' in c]
            macd_hist = [c for c in macd_cols if 'MACDh' in c]
            if macd_line: g['MACD'] = macd[macd_line[0]]
            if macd_signal: g['MACD_signal'] = macd[macd_signal[0]]
            if macd_hist: g['MACD_histogram'] = macd[macd_hist[0]]
        g['ROC_10'] = ta.roc(g['Close'], length=10)
        stoch = ta.stoch(g['High'], g['Low'], g['Close'])
        if stoch is not None and not stoch.empty:
            stoch_cols = stoch.columns.tolist()
            stoch_k = [c for c in stoch_cols if 'STOCHk' in c]
            if stoch_k: g['stochastic_14'] = stoch[stoch_k[0]]
        g['volume_SMA_20'] = ta.sma(g['Volume'], length=20)
        g['volume_ratio_20'] = g['Volume'] / (g['volume_SMA_20'] + 1e-9)
        g['volume_change'] = g['Volume'].pct_change(1)
        g['OBV'] = ta.obv(g['Close'], g['Volume'])
        g['MFI_14'] = ta.mfi(g['High'], g['Low'], g['Close'], g['Volume'], length=14)
        g['daily_range'] = (g['High'] - g['Low']) / (g['Close'] + 1e-9)
        g['close_position'] = (g['Close'] - g['Low']) / (g['High'] - g['Low'] + 1e-9)
        g['upper_wick'] = (g['High'] - np.maximum(g['Close'], g['Open'])) / (g['Close'] + 1e-9)
        g['lower_wick'] = (np.minimum(g['Close'], g['Open']) - g['Low']) / (g['Close'] + 1e-9)
        g['body_size'] = np.abs(g['Close'] - g['Open']) / (g['Open'] + 1e-9)
        adx = ta.adx(g['High'], g['Low'], g['Close'], length=14)
        if adx is not None and not adx.empty:
            adx_cols = adx.columns.tolist()
            adx_col = [c for c in adx_cols if c.startswith('ADX')]
            if adx_col: g['ADX_14'] = adx[adx_col[0]]
            
            
            
        ## TARGET
        g['raw_return'] = g['Close'].shift(-5) / g['Close'] - 1
        g['momentum'] = (g['Close'].shift(-5) / g['Close'] - 1) * 100    
        g.dropna(subset=['momentum'], inplace=True)    
        feature_dfs.append(g)

    final_df = pd.concat(feature_dfs, ignore_index=True)
    final_df = final_df.dropna(subset=['SMA_50', 'momentum'])
    output_file = f"{DATA_DIR}/stock_data.jsonl"
    final_df.to_json(output_file, orient='records', lines=True, date_format='iso')
    print(f"Stock features saved to {output_file}")
    return final_df


def preprocess_to_tensor(df, device="cuda"):
    feature_cols = df.drop(columns=['momentum', 'raw_return', 'Date', 'ticker', 'Close', 'High', 'Low', 'Open', 'Volume'], errors='ignore')
    feature_cols = feature_cols.select_dtypes(include=[np.number])
    
    clean_data = feature_cols.replace([np.inf, -np.inf], np.nan).ffill().fillna(0).to_numpy()
    
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(clean_data)
    scaled_data = np.nan_to_num(scaled_data, nan=0.0, posinf=0.0, neginf=0.0)
    
    return scaler, torch.tensor(scaled_data, dtype=torch.float32).to(device)

if __name__ == "__main__":    final_df = create_features()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    scaler, tensor = preprocess_to_tensor(final_df, device=device)
    print(f"Tensor Shape: {tensor.shape}")