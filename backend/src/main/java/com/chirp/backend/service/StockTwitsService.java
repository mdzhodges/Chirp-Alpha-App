package com.chirp.backend.service;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

@Service
public class StockTwitsService {
    
    private final HttpClient httpClient;
    private final RedisCacheService cacheService;
    private static final String STOCKTWITS_URL_TEMPLATE = "https://api.stocktwits.com/api/2/streams/symbol/%s.json";

    public StockTwitsService(RedisCacheService cacheService) {
        this.httpClient = HttpClient.newHttpClient();
        this.cacheService = cacheService;
    }

    public String getFeedForTicker(String symbol) {
        if (symbol == null || symbol.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Symbol is required");
        }

        String normalized = symbol.trim().toUpperCase();
        String cacheKey = "stocktwits:feed:" + normalized;

        return cacheService.getOrCompute(cacheKey, String.class, Duration.ofMinutes(15), () -> fetchFeed(normalized));
    }

    private String fetchFeed(String symbol) {
        String encodedSymbol = URLEncoder.encode(symbol.trim(), StandardCharsets.UTF_8);
        URI uri = URI.create(String.format(STOCKTWITS_URL_TEMPLATE, encodedSymbol));

        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri)
                .GET()
                .header("Accept", "application/json")
                .build();

        try {
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() != 200) {
                throw new ResponseStatusException(
                    HttpStatus.valueOf(response.statusCode()), 
                    "StockTwits API returned status: " + response.statusCode()
                );
            }

            // Return the raw JSON string to be passed directly to the React frontend
            return response.body();
            
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Request to StockTwits was interrupted", e);
        } catch (IOException e) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Failed to reach StockTwits API", e);
        }
    }
}
