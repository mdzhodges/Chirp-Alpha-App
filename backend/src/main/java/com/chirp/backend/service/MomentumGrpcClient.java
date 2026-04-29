package com.chirp.backend.service;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import momentum.BatchMomentumRequest;
import momentum.BatchMomentumResponse;
import momentum.MomentumRequest;
import momentum.MomentumResponse;
import momentum.MomentumServiceGrpc;
import momentum.OHLCV;
import momentum.OHLCVList;
import org.springframework.stereotype.Service;

import javax.annotation.PreDestroy;
import java.util.List;
import java.util.Map;

@Service
public class MomentumGrpcClient {

    private final ManagedChannel channel;
    private final MomentumServiceGrpc.MomentumServiceBlockingStub blockingStub;

    public MomentumGrpcClient() {
        this.channel = ManagedChannelBuilder.forAddress("localhost", 50051)
                .usePlaintext()
                .build();
        this.blockingStub = MomentumServiceGrpc.newBlockingStub(channel);
    }

    public float predictMomentum(String ticker, List<OHLCV> stockHistory, Map<String, List<OHLCV>> marketHistory, List<String> tweets, int offset) {
        MomentumRequest request = MomentumRequest.newBuilder()
                .setTicker(ticker)
                .addAllStockHistory(stockHistory)
                .addAllTweets(tweets)
                .setOffset(offset)
                .putAllMarketHistory(buildMarketHistoryMap(marketHistory))
                .build();

        MomentumResponse response = blockingStub.predictMomentum(request);
        return response.getMomentum();
    }

    public List<Float> batchPredictMomentum(String ticker, List<OHLCV> stockHistory, Map<String, List<OHLCV>> marketHistory, List<String> tweets, List<Integer> offsets) {
        BatchMomentumRequest request = BatchMomentumRequest.newBuilder()
                .setTicker(ticker)
                .addAllStockHistory(stockHistory)
                .addAllTweets(tweets)
                .addAllOffsets(offsets)
                .putAllMarketHistory(buildMarketHistoryMap(marketHistory))
                .build();

        BatchMomentumResponse response = blockingStub.batchPredictMomentum(request);
        return response.getMomentumsList();
    }

    private Map<String, OHLCVList> buildMarketHistoryMap(Map<String, List<OHLCV>> marketHistory) {
        Map<String, OHLCVList> map = new java.util.HashMap<>();
        marketHistory.forEach((symbol, points) -> {
            map.put(symbol, OHLCVList.newBuilder().addAllPoints(points).build());
        });
        return map;
    }

    @PreDestroy
    public void shutdown() {
        channel.shutdown();
    }
}
