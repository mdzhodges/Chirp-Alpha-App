package com.chirp.backend.service;

import org.springframework.beans.factory.annotation.Value;
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
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

@Service
public class FinnhubNewsService {

    private final HttpClient httpClient;
    private final RedisCacheService cacheService;
    private final String apiKey;
    private final Duration newsTtl;
    private static final String FINNHUB_URL_TEMPLATE = "https://finnhub.io/api/v1/company-news?symbol=%s&from=%s&to=%s&token=%s";

    public FinnhubNewsService(RedisCacheService cacheService, 
                             @Value("${FINNHUB_API_KEY:}") String apiKey,
                             @Value("${cache.redis.finnhub-news-ttl:PT15M}") Duration newsTtl) {
        this.httpClient = HttpClient.newHttpClient();
        this.cacheService = cacheService;
        this.apiKey = apiKey;
        this.newsTtl = newsTtl;
    }

    public String getNewsForTicker(String symbol) {
        if (symbol == null || symbol.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Symbol is required");
        }

        if (apiKey == null || apiKey.isBlank()) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Finnhub API key is not configured");
        }

        String normalized = symbol.trim().toUpperCase();
        String cacheKey = "finnhub:news:" + normalized;

        return cacheService.getOrCompute(cacheKey, String.class, newsTtl, () -> fetchNews(normalized));
    }

    private String fetchNews(String symbol) {
        String encodedSymbol = URLEncoder.encode(symbol, StandardCharsets.UTF_8);
        
        // Fetch news from the last 7 days
        LocalDate to = LocalDate.now();
        LocalDate from = to.minusDays(7);
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd");

        URI uri = URI.create(String.format(FINNHUB_URL_TEMPLATE, 
            encodedSymbol, 
            from.format(formatter), 
            to.format(formatter), 
            apiKey
        ));

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
                    "Finnhub API returned status: " + response.statusCode() + " - " + response.body()
                );
            }

            return response.body();
            
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Request to Finnhub was interrupted", e);
        } catch (IOException e) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Failed to reach Finnhub API", e);
        }
    }
}
