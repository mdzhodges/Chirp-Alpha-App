package com.chirp.backend.service;

import com.chirp.backend.api.dto.TickerResponse;
import com.chirp.backend.api.dto.TickerResponse.GraphPoint;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.beans.factory.annotation.Value;

import java.io.IOException;
import java.math.BigDecimal;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class YahooFinanceTickerService {
    private static final Logger log = LoggerFactory.getLogger(YahooFinanceTickerService.class);
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final YahooAuthService authService;
    private final MomentumGrpcClient momentumClient;
    private final StockTwitsService stockTwitsService;
    private final RedisCacheService cacheService;

    @Value("${LOGO_DEV_API_KEY:}")
    private String logoDevApiKey;

    @Value("${cache.redis.ticker-ttl:PT5M}")
    private Duration tickerTtl;

    @Value("${cache.redis.momentum-ttl:PT1H}")
    private Duration momentumTtl;

    @org.springframework.beans.factory.annotation.Autowired
    public YahooFinanceTickerService(ObjectMapper objectMapper, YahooAuthService authService, 
                                    MomentumGrpcClient momentumClient, StockTwitsService stockTwitsService,
                                    RedisCacheService cacheService) {
        this.httpClient = authService.getHttpClient();
        this.objectMapper = objectMapper;
        this.authService = authService;
        this.momentumClient = momentumClient;
        this.stockTwitsService = stockTwitsService;
        this.cacheService = cacheService;
    }

    public TickerResponse fetch(String symbol, String modelType, boolean skipMomentum) {
        log.debug("Fetching ticker data for: {} (skipMomentum={})", symbol, skipMomentum);

        String normalizedSymbol = normalizeSymbol(symbol);
        String normalizedModelType = normalizeModelType(modelType);
        String cacheKey = "ticker:snapshot:" + normalizedSymbol + ":" + normalizedModelType + ":skipMomentum:" + skipMomentum;

        Duration ttl = skipMomentum ? tickerTtl : momentumTtl;
        return cacheService.getOrCompute(cacheKey, TickerResponse.class, ttl,
                () -> computeTickerResponse(normalizedSymbol, normalizedModelType, skipMomentum));
    }

    private TickerResponse computeTickerResponse(String symbol, String modelType, boolean skipMomentum) {
        JsonNode chartRoot = fetchChartDataWithRetry(symbol);
        JsonNode result = chartRoot.path("chart").path("result").get(0);
        if (result == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Symbol not found: " + symbol);
        }

        JsonNode meta = result.path("meta");
        List<GraphPoint> graphData = parseGraphData(result);

        JsonNode summary = fetchQuoteSummaryWithRetry(symbol);

        BigDecimal currentMomentum = BigDecimal.ZERO;
        List<TickerResponse.MomentumPoint> momentumHistory = new ArrayList<>();
        List<String> signals = new ArrayList<>();
        
        if (!skipMomentum) {
            try {
                MomentumData momentumData = fetchMomentumData(symbol, modelType);
                if (momentumData != null) {
                    currentMomentum = momentumData.current;
                    momentumHistory = momentumData.history;
                    signals = momentumData.signals;
                }
            } catch (Exception e) {
                log.error("Failed to fetch momentum for {}: {}", symbol, e.getMessage());
            }
        }

        return mapToTickerResponse(symbol, meta, summary, graphData, currentMomentum, momentumHistory, getModelStats(modelType), signals);
    }

    public record MomentumData(BigDecimal current, List<TickerResponse.MomentumPoint> history, List<String> signals) {}

    public MomentumData fetchMomentumData(String symbol, String modelType) {
        String normalizedSymbol = normalizeSymbol(symbol);
        String normalizedModelType = normalizeModelType(modelType);
        String cacheKey = "ticker:momentum:" + normalizedSymbol + ":" + normalizedModelType;
        return cacheService.getOrCompute(cacheKey, MomentumData.class, momentumTtl,
                () -> computeMomentumData(normalizedSymbol, normalizedModelType));
    }

    private MomentumData computeMomentumData(String symbol, String modelType) {
        JsonNode stockHistory = fetchDailyChartData(symbol, "120d");
        Map<String, JsonNode> marketHistory = new HashMap<>();
        for (String m : List.of("SPY", "QQQ", "DIA", "^VIX")) {
            marketHistory.put(m, fetchDailyChartData(m, "120d"));
        }

        // Fetch tweets and filter for data leakage
        String tweetsJson = stockTwitsService.getFeedForTicker(symbol);
        List<String> tweets = new ArrayList<>();
        // Current momentum is predicted from 5 days ago
        Instant cutoff = Instant.now().minus(java.time.Duration.ofDays(5));
        
        try {
            JsonNode tweetsRoot = objectMapper.readTree(tweetsJson);
            JsonNode messages = tweetsRoot.path("messages");
            if (messages.isArray()) {
                for (JsonNode msg : messages) {
                    JsonNode user = msg.path("user");
                    int followers = user.path("followers").asInt(0);
                    boolean isOfficial = user.path("official").asBoolean(false);

                    // Filter for high-quality accounts (Min 1000 followers or Official)
                    if (followers >= 500 || isOfficial) {
                        tweets.add(msg.path("body").asText());
                    }
                }
            }
        } catch (IOException e) {
            log.warn("Failed to parse tweets for momentum: {}", e.getMessage());
        }

        List<momentum.OHLCV> stockOhlcv = convertToOhlcv(stockHistory.path("chart").path("result").get(0));
        Map<String, List<momentum.OHLCV>> marketOhlcv = new HashMap<>();
        marketHistory.forEach((s, node) -> {
            marketOhlcv.put(s, convertToOhlcv(node.path("chart").path("result").get(0)));
        });

        // Current prediction with signals
        MomentumGrpcClient.PredictionResult singlePred = momentumClient.predictMomentum(symbol, stockOhlcv, marketOhlcv, tweets, 0, modelType);

        // We want a trend for the last 30 trading days
        List<Integer> offsets = new ArrayList<>();
        for (int i = 0; i <= 30; i++) offsets.add(i);
        List<Float> preds = momentumClient.batchPredictMomentum(symbol, stockOhlcv, marketOhlcv, tweets, offsets, modelType);

        List<TickerResponse.MomentumPoint> historyPoints = new ArrayList<>();
        for (int i = 0; i < offsets.size() && i < preds.size(); i++) {
            int offset = offsets.get(i);
            if (offset < stockOhlcv.size()) {
                Instant ts = Instant.parse(stockOhlcv.get(stockOhlcv.size() - 1 - offset).getDate());
                historyPoints.add(new TickerResponse.MomentumPoint(ts, BigDecimal.valueOf(preds.get(i))));
            }
        }

        BigDecimal current = singlePred != null ? BigDecimal.valueOf(singlePred.momentum()) : (preds.isEmpty() ? BigDecimal.ZERO : BigDecimal.valueOf(preds.get(0)));
        List<String> signals = singlePred != null ? singlePred.signals() : new ArrayList<>();
        return new MomentumData(current, historyPoints, signals);
    }

    private String normalizeSymbol(String symbol) {
        if (symbol == null || symbol.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Symbol is required");
        }
        return symbol.trim().toUpperCase();
    }

    private String normalizeModelType(String modelType) {
        return (modelType == null || modelType.isBlank()) ? "balanced" : modelType.trim().toLowerCase();
    }

    private JsonNode fetchDailyChartData(String symbol, String range) {
        return executeWithRetry(symbol, "chart-daily", (s, isRetry) -> {
            String encodedSymbol = URLEncoder.encode(s, StandardCharsets.UTF_8);
            String url = String.format("https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=1d&range=%s&includePrePost=true&crumb=%s",
                    encodedSymbol, range, authService.getCrumb());
            return buildRequest(url);
        });
    }

    private List<momentum.OHLCV> convertToOhlcv(JsonNode result) {
        List<momentum.OHLCV> points = new ArrayList<>();
        if (result == null || result.isMissingNode()) return points;
        
        JsonNode timestamps = result.path("timestamp");
        JsonNode quote = result.path("indicators").path("quote").get(0);
        JsonNode adjCloseNode = result.path("indicators").path("adjclose");
        JsonNode adjCloses = (adjCloseNode != null && adjCloseNode.isArray() && !adjCloseNode.isEmpty()) ? adjCloseNode.get(0).path("adjclose") : null;
        
        JsonNode opens = quote.path("open");
        JsonNode highs = quote.path("high");
        JsonNode lows = quote.path("low");
        JsonNode closes = quote.path("close");
        JsonNode volumes = quote.path("volume");

        if (timestamps.isArray()) {
            for (int i = 0; i < timestamps.size(); i++) {
                if (closes.get(i).isNull()) continue;
                
                points.add(momentum.OHLCV.newBuilder()
                        .setDate(Instant.ofEpochSecond(timestamps.get(i).asLong()).toString())
                        .setOpen(opens.get(i).asDouble())
                        .setHigh(highs.get(i).asDouble())
                        .setLow(lows.get(i).asDouble())
                        .setClose(closes.get(i).asDouble())
                        .setVolume(volumes.get(i).asDouble())
                        .setAdjClose(adjCloses != null && adjCloses.has(i) ? adjCloses.get(i).asDouble() : closes.get(i).asDouble())
                        .build());
            }
        }
        return points;
    }

    private JsonNode fetchChartDataWithRetry(String symbol) {
        return executeWithRetry(symbol, "chart", (s, isRetry) -> {
            String encodedSymbol = URLEncoder.encode(s, StandardCharsets.UTF_8);
            String url = String.format("https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=60m&range=7d&includePrePost=true&crumb=%s",
                    encodedSymbol, authService.getCrumb());
            return buildRequest(url);
        });
    }

    private JsonNode fetchQuoteSummaryWithRetry(String symbol) {
        return executeWithRetry(symbol, "quoteSummary", (s, isRetry) -> {
            String encodedSymbol = URLEncoder.encode(s, StandardCharsets.UTF_8);
            String url = String.format("https://query1.finance.yahoo.com/v10/finance/quoteSummary/%s?modules=summaryDetail,defaultKeyStatistics,price,assetProfile&crumb=%s",
                    encodedSymbol, authService.getCrumb());
            return buildRequest(url);
        });
    }

    private HttpRequest buildRequest(String url) {
        return HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("User-Agent", YahooAuthService.USER_AGENT)
                .GET()
                .build();
    }

    private JsonNode executeWithRetry(String symbol, String endpointName, RequestBuilder requestBuilder) {
        return executeAttempt(symbol, endpointName, requestBuilder, false);
    }

    private JsonNode executeAttempt(String symbol, String endpointName, RequestBuilder requestBuilder, boolean isRetry) {
        HttpRequest request = requestBuilder.build(symbol, isRetry);
        log.debug("Calling {} endpoint (retry={}): {}", endpointName, isRetry, request.uri());

        try {
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            
            if (response.statusCode() == 404) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Symbol not found: " + symbol);
            }

            if (response.statusCode() == 401 || response.statusCode() == 403 || response.statusCode() == 429) {
                if (!isRetry) {
                    log.warn("{} endpoint failed with {}. Refreshing auth and retrying...", endpointName, response.statusCode());
                    authService.invalidate();
                    authService.refresh();
                    return executeAttempt(symbol, endpointName, requestBuilder, true);
                } else {
                    log.error("{} failed after retry. Status: {}, Body: {}", endpointName, response.statusCode(), response.body());
                    if ("quoteSummary".equals(endpointName)) {
                        return objectMapper.createObjectNode();
                    }
                    throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Yahoo Finance " + endpointName + " request failed after auth refresh (" + response.statusCode() + ")");
                }
            }

            if (response.statusCode() != 200) {
                log.error("{} endpoint failed. Status: {}, Body: {}", endpointName, response.statusCode(), response.body());
                if ("quoteSummary".equals(endpointName)) {
                    return objectMapper.createObjectNode();
                }
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Yahoo Finance " + endpointName + " request failed (" + response.statusCode() + ")");
            }

            return objectMapper.readTree(response.body());
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Yahoo Finance request interrupted", e);
            }
            if ("quoteSummary".equals(endpointName)) {
                return objectMapper.createObjectNode();
            }
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Failed to connect to Yahoo Finance", e);
        }
    }

    private List<GraphPoint> parseGraphData(JsonNode result) {
        List<GraphPoint> points = new ArrayList<>();
        JsonNode timestamps = result.path("timestamp");
        JsonNode quote = result.path("indicators").path("quote").get(0);
        JsonNode opens = quote.path("open");
        JsonNode highs = quote.path("high");
        JsonNode lows = quote.path("low");
        JsonNode closes = quote.path("close");

        if (timestamps.isArray() && closes.isArray()) {
            for (int i = 0; i < timestamps.size(); i++) {
                JsonNode closeNode = closes.get(i);
                if (!closeNode.isNull() && closeNode.isNumber()) {
                    long epochSeconds = timestamps.get(i).asLong();
                    points.add(new GraphPoint(
                            Instant.ofEpochSecond(epochSeconds),
                            asBigDecimal(opens.get(i)),
                            asBigDecimal(highs.get(i)),
                            asBigDecimal(lows.get(i)),
                            closeNode.decimalValue()
                    ));
                }
            }
        }
        return points;
    }

    private TickerResponse mapToTickerResponse(String symbol, JsonNode meta, JsonNode summary, List<GraphPoint> graphData, BigDecimal momentum, List<TickerResponse.MomentumPoint> momentumHistory, TickerResponse.ModelStats modelStats, List<String> signals) {
        JsonNode quoteRes = summary.path("quoteSummary").path("result").get(0);
        JsonNode priceMod = quoteRes.path("price");
        JsonNode summaryDetail = quoteRes.path("summaryDetail");
        JsonNode keyStats = quoteRes.path("defaultKeyStatistics");
        JsonNode assetProfile = quoteRes.path("assetProfile");
    
        String website = assetProfile.path("website").asText(null);
        String companyName = priceMod.path("longName").asText(null);
        String description = assetProfile.path("longBusinessSummary").asText(null);
    
        String domain = null;
        if (website != null && !website.isEmpty()) {
            domain = website.replaceAll("https?://(www\\.)?", "").replaceAll("/.*", "");
        }
        String logoUrl = domain != null
            ? "https://img.logo.dev/" + domain + "?token=" + logoDevApiKey + "&format=png"
            : "https://img.logo.dev/" + symbol.toLowerCase() + ".com?token=" + logoDevApiKey + "&format=png";
        
        return new TickerResponse(
                meta.path("symbol").asText(symbol),
                priceMod.path("longName").asText(null),
                meta.path("currency").asText(null),
                meta.path("exchangeName").asText(null),
                asBigDecimal(meta.path("regularMarketPrice")),
                asBigDecimal(priceMod.path("regularMarketChange")),
                asBigDecimal(priceMod.path("regularMarketChangePercent")),
                asBigDecimal(priceMod.path("regularMarketOpen")),
                asBigDecimal(meta.path("chartPreviousClose")),
                asBigDecimal(meta.path("regularMarketDayHigh")),
                asBigDecimal(meta.path("regularMarketDayLow")),
                meta.path("regularMarketVolume").asLong(0L),
                summaryDetail.path("averageVolume").path("raw").asLong(0L),
                asBigDecimal(summaryDetail.path("marketCap").path("raw")),
                asBigDecimal(summaryDetail.path("trailingPE").path("raw")),
                asBigDecimal(keyStats.path("forwardPE").path("raw")),
                asBigDecimal(keyStats.path("trailingEps").path("raw")),
                asBigDecimal(summaryDetail.path("dividendYield").path("raw")),
                asBigDecimal(summaryDetail.path("beta").path("raw")),
                asBigDecimal(keyStats.path("priceToBook").path("raw")),
                asBigDecimal(keyStats.path("profitMargins").path("raw")),
                asBigDecimal(keyStats.path("enterpriseValue").path("raw")),
                keyStats.path("sharesOutstanding").path("raw").asLong(0L),
                asBigDecimal(meta.path("fiftyTwoWeekHigh")),
                asBigDecimal(meta.path("fiftyTwoWeekLow")),
                momentum,
                momentumHistory,
                graphData,
                modelStats,
                signals,
                description,
                logoUrl,
                Instant.now()
        );
    }

    private BigDecimal asBigDecimal(JsonNode node) {
        if (node.isNull() || node.isMissingNode()) return null;
        if (node.isNumber()) return node.decimalValue();
        JsonNode raw = node.path("raw");
        if (raw.isNumber()) return raw.decimalValue();
        return null;
    }

    @FunctionalInterface
    private interface RequestBuilder {
        HttpRequest build(String symbol, boolean isRetry);
    }

    private TickerResponse.ModelStats getModelStats(String modelType) {
        String type = (modelType == null || modelType.isEmpty()) ? "balanced" : modelType.toLowerCase();
        return switch (type) {
            case "bullish" -> new TickerResponse.ModelStats("Bullish", 
                new BigDecimal("0.5176"), new BigDecimal("0.6960"), new BigDecimal("0.3432"), new BigDecimal("0.0494"));
            case "bearish" -> new TickerResponse.ModelStats("Bearish", 
                new BigDecimal("0.4932"), new BigDecimal("0.3842"), new BigDecimal("0.6335"), new BigDecimal("0.0184"));
            case "high_ic" -> new TickerResponse.ModelStats("High IC", 
                new BigDecimal("0.5206"), new BigDecimal("0.5796"), new BigDecimal("0.4721"), new BigDecimal("0.0668"));
            case "ensemble", "consensus" -> new TickerResponse.ModelStats("Consensus", 
                new BigDecimal("0.5093"), new BigDecimal("0.5425"), new BigDecimal("0.4934"), new BigDecimal("0.0495"));
            default -> new TickerResponse.ModelStats("Balanced", 
                new BigDecimal("0.5059"), new BigDecimal("0.5102"), new BigDecimal("0.5247"), new BigDecimal("0.0634"));
        };
    }

}
