import grpc
import momentum_pb2
import momentum_pb2_grpc
import datetime

def run():
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = momentum_pb2_grpc.MomentumServiceStub(channel)
        
        # Create some dummy stock history (60 days)
        stock_history = []
        base_date = datetime.date(2023, 1, 1)
        for i in range(60):
            d = base_date + datetime.timedelta(days=i)
            stock_history.append(momentum_pb2.OHLCV(
                date=d.isoformat(),
                open=150.0 + i,
                high=155.0 + i,
                low=148.0 + i,
                close=152.0 + i,
                volume=1000000,
                adj_close=152.0 + i
            ))
            
        # Create some dummy market history
        market_history = {}
        for ticker in ["SPY", "QQQ", "DIA", "^VIX"]:
            points = []
            for i in range(60):
                d = base_date + datetime.timedelta(days=i)
                points.append(momentum_pb2.OHLCV(
                    date=d.isoformat(),
                    open=400.0 + i,
                    high=405.0 + i,
                    low=398.0 + i,
                    close=402.0 + i,
                    volume=10000000,
                    adj_close=402.0 + i
                ))
            market_history[ticker] = momentum_pb2.OHLCVList(points=points)
            
        request = momentum_pb2.MomentumRequest(
            ticker="AAPL",
            stock_history=stock_history,
            market_history=market_history,
            tweets=["AAPL is looking strong today!", "Bullish on Apple"]
        )
        
        print("Sending request to gRPC server...")
        response = stub.PredictMomentum(request)
        print(f"Momentum Response: {response.momentum}")

if __name__ == '__main__':
    run()
