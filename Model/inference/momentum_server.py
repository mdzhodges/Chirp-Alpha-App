import grpc
from concurrent import futures
import time
import torch
import pandas as pd
import numpy as np
import joblib
import os
import sys

# Add Model directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import momentum_pb2
import momentum_pb2_grpc
from architecture.models.stock_nn import StockNetwork
from architecture.models.index_nn import IndexNetwork
from architecture.models.final_output import OutputNN
from architecture.models.encoder import Encoder
from preprocessing.combined_jsonl import create_stock_features, create_spy_features

class MomentumService(momentum_pb2_grpc.MomentumServiceServicer):
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Using device: {self.device}")
        
        # Load assets
        assets_dir = os.path.join(os.path.dirname(__file__), "assets")
        self.stock_scaler = joblib.load(os.path.join(assets_dir, "stock_scaler.pkl"))
        self.spy_scaler = joblib.load(os.path.join(assets_dir, "spy_scaler.pkl"))
        self.stock_cols = joblib.load(os.path.join(assets_dir, "stock_cols.pkl"))
        self.spy_cols = joblib.load(os.path.join(assets_dir, "spy_cols.pkl"))
        
        # Initialize models
        self.encoder = Encoder().to(self.device)
        self.stock_network = StockNetwork(input_dim=37).to(self.device)
        self.index_network = IndexNetwork(input_dim=42).to(self.device)
        self.output_network = OutputNN(816).to(self.device)
        
        # Load weights
        weights_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../Model/graphs/1e-06_0.1_0.005/best_model_weights.pt"))
        print(f"Loading weights from {weights_path}...")
        weights = torch.load(weights_path, map_location=self.device, weights_only=False)
        
        if weights.get('encoder'):
            self.encoder.load_state_dict(weights['encoder'])
        self.stock_network.load_state_dict(weights['stock_network'])
        self.index_network.load_state_dict(weights['index_network'])
        self.output_network.load_state_dict(weights['output_network'])
        
        self.encoder.eval()
        self.stock_network.eval()
        self.index_network.eval()
        self.output_network.eval()
        print("Models loaded and set to eval mode.")

    def PredictMomentum(self, request, context):
        try:
            # 1. Process Stock History
            stock_data_list = []
            for p in request.stock_history:
                stock_data_list.append({
                    "Date": p.date, 
                    "Open": p.open, 
                    "High": p.high, 
                    "Low": p.low, 
                    "Close": p.close, 
                    "Volume": p.volume, 
                    "Adj Close": p.adj_close,
                    "ticker": request.ticker
                })
            
            stock_df = pd.DataFrame(stock_data_list)
            # We need at least 50+ rows for some indicators like SMA_50
            if len(stock_df) < 50:
                print(f"Warning: insufficient stock history ({len(stock_df)} rows)")
            
            stock_feats = create_stock_features(stock_df, training=False)
            if stock_feats.empty:
                print("Stock features empty after processing")
                return momentum_pb2.MomentumResponse(momentum=0.0)
            
            # Use the requested offset for prediction
            offset = max(0, request.offset)
            if offset >= len(stock_feats):
                print(f"Warning: offset {offset} out of bounds for stock_feats (length {len(stock_feats)})")
                offset = 0
            
            idx = -1 - offset
            latest_stock = stock_feats.iloc[idx : idx + 1 if idx != -1 else None]
            s_df = latest_stock[self.stock_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            s_tensor = torch.tensor(self.stock_scaler.transform(s_df.to_numpy()), device=self.device, dtype=torch.float32)

            # 2. Process Market History
            market_parts = []
            for ticker, history in request.market_history.items():
                part_data = []
                for p in history.points:
                    part_data.append({
                        "Date": p.date, 
                        f"{ticker}_Open": p.open, 
                        f"{ticker}_High": p.high, 
                        f"{ticker}_Low": p.low, 
                        f"{ticker}_Close": p.close, 
                        f"{ticker}_Volume": p.volume
                    })
                market_parts.append(pd.DataFrame(part_data))
            
            if not market_parts:
                print("No market history provided")
                return momentum_pb2.MomentumResponse(momentum=0.0)
            
            market_df = market_parts[0]
            for p in market_parts[1:]:
                market_df = market_df.merge(p, on="Date", how="outer")
            
            market_df["Date"] = pd.to_datetime(market_df["Date"])
            market_df = market_df.sort_values("Date")
            market_feats = create_spy_features(market_df)
            
            # Ensure all expected columns are present
            for c in self.spy_cols:
                if c not in market_feats.columns:
                    market_feats[c] = 0.0
            
            if offset >= len(market_feats):
                print(f"Warning: offset {offset} out of bounds for market_feats (length {len(market_feats)})")
                offset = 0
            
            m_idx = -1 - offset
            latest_market = market_feats.iloc[m_idx : m_idx + 1 if m_idx != -1 else None]
            i_df = latest_market[self.spy_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            i_tensor = torch.tensor(self.spy_scaler.transform(i_df.to_numpy()), device=self.device, dtype=torch.float32)

            # 3. Process Tweets
            if request.tweets:
                text_feat = self.encoder(list(request.tweets)).mean(dim=0, keepdim=True)
            else:
                text_feat = self.output_network.no_tweet_embedding.unsqueeze(0)

            # 4. Inference
            with torch.no_grad():
                s_feat = self.stock_network(s_tensor)
                i_feat = self.index_network(i_tensor)
                combined = torch.cat((s_feat, i_feat, text_feat), dim=1)
                pred = self.output_network(combined).squeeze().item()

            return momentum_pb2.MomentumResponse(momentum=float(pred))
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return momentum_pb2.MomentumResponse()

    def BatchPredictMomentum(self, request, context):
        try:
            # 1. Process Stock History
            stock_data_list = []
            for p in request.stock_history:
                stock_data_list.append({
                    "Date": p.date, 
                    "Open": p.open, 
                    "High": p.high, 
                    "Low": p.low, 
                    "Close": p.close, 
                    "Volume": p.volume, 
                    "Adj Close": p.adj_close,
                    "ticker": request.ticker
                })
            
            stock_df = pd.DataFrame(stock_data_list)
            stock_feats = create_stock_features(stock_df, training=False)
            
            # 2. Process Market History
            market_parts = []
            for ticker, history in request.market_history.items():
                part_data = []
                for p in history.points:
                    part_data.append({
                        "Date": p.date, 
                        f"{ticker}_Open": p.open, 
                        f"{ticker}_High": p.high, 
                        f"{ticker}_Low": p.low, 
                        f"{ticker}_Close": p.close, 
                        f"{ticker}_Volume": p.volume
                    })
                market_parts.append(pd.DataFrame(part_data))
            
            market_df = market_parts[0]
            for p in market_parts[1:]:
                market_df = market_df.merge(p, on="Date", how="outer")
            
            market_df["Date"] = pd.to_datetime(market_df["Date"])
            market_df = market_df.sort_values("Date")
            market_feats = create_spy_features(market_df)
            for c in self.spy_cols:
                if c not in market_feats.columns:
                    market_feats[c] = 0.0

            # 3. Process Tweets
            if request.tweets:
                text_feat = self.encoder(list(request.tweets)).mean(dim=0, keepdim=True)
            else:
                text_feat = self.output_network.no_tweet_embedding.unsqueeze(0)

            results = []
            for offset in request.offsets:
                off = max(0, offset)
                
                # Stock features for this offset
                s_idx = -1 - off
                if abs(s_idx) > len(stock_feats):
                    results.append(0.0)
                    continue
                latest_stock = stock_feats.iloc[s_idx : s_idx + 1 if s_idx != -1 else None]
                s_df = latest_stock[self.stock_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
                s_tensor = torch.tensor(self.stock_scaler.transform(s_df.to_numpy()), device=self.device, dtype=torch.float32)

                # Market features for this offset
                m_idx = -1 - off
                if abs(m_idx) > len(market_feats):
                    results.append(0.0)
                    continue
                latest_market = market_feats.iloc[m_idx : m_idx + 1 if m_idx != -1 else None]
                i_df = latest_market[self.spy_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
                i_tensor = torch.tensor(self.spy_scaler.transform(i_df.to_numpy()), device=self.device, dtype=torch.float32)

                with torch.no_grad():
                    s_feat = self.stock_network(s_tensor)
                    i_feat = self.index_network(i_tensor)
                    combined = torch.cat((s_feat, i_feat, text_feat), dim=1)
                    pred = self.output_network(combined).squeeze().item()
                    results.append(float(pred))

            return momentum_pb2.BatchMomentumResponse(momentums=results)

        except Exception as e:
            import traceback
            traceback.print_exc()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return momentum_pb2.BatchMomentumResponse()

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    momentum_pb2_grpc.add_MomentumServiceServicer_to_server(MomentumService(), server)
    server.add_insecure_port('[::]:50051')
    print("Starting gRPC server on port 50051...")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
