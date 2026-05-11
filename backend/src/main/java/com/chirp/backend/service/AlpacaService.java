package com.chirp.backend.service;

import com.chirp.backend.api.dto.AlpacaDashboardResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.Map;

@Service
public class AlpacaService {

    private final RestTemplate restTemplate;

    @Value("${alpaca.bullish.key}")
    private String bullishKey;
    @Value("${alpaca.bullish.secret}")
    private String bullishSecret;

    @Value("${alpaca.balanced.key}")
    private String balancedKey;
    @Value("${alpaca.balanced.secret}")
    private String balancedSecret;

    @Value("${alpaca.bearish.key}")
    private String bearishKey;
    @Value("${alpaca.bearish.secret}")
    private String bearishSecret;

    @Value("${alpaca.base-url}")
    private String baseUrl;

    public AlpacaService() {
        this.restTemplate = new RestTemplate();
    }

    public AlpacaDashboardResponse getDashboardData() {
        return new AlpacaDashboardResponse(
            fetchAccountData("bullish", bullishKey, bullishSecret),
            fetchAccountData("balanced", balancedKey, balancedSecret),
            fetchAccountData("bearish", bearishKey, bearishSecret)
        );
    }

    private AlpacaDashboardResponse.AlpacaAccountData fetchAccountData(String strategy, String key, String secret) {
        if (key == null || key.isEmpty() || secret == null || secret.isEmpty()) {
            System.out.println("Alpaca keys missing for strategy: " + strategy);
            return null;
        }

        try {
            System.out.println("Fetching Alpaca data for strategy: " + strategy);
            HttpHeaders headers = new HttpHeaders();
            headers.set("APCA-API-KEY-ID", key);
            headers.set("APCA-API-SECRET-KEY", secret);
            HttpEntity<String> entity = new HttpEntity<>(headers);

            // Fetch Account Info
            ResponseEntity<Map> accountResponse = restTemplate.exchange(
                baseUrl + "/v2/account",
                HttpMethod.GET,
                entity,
                Map.class
            );

            Map<String, Object> accountMap = accountResponse.getBody();
            if (accountMap == null) {
                System.err.println("Empty account response for strategy: " + strategy);
                return null;
            }

            Double equity = Double.valueOf(accountMap.get("equity").toString());
            Double buyingPower = Double.valueOf(accountMap.getOrDefault("buying_power", accountMap.getOrDefault("buyingPower", 0.0)).toString());

            // Fetch Portfolio History (15Min to allow 90Min filtering in frontend)
            ResponseEntity<AlpacaDashboardResponse.PortfolioHistory> historyResponse = restTemplate.exchange(
                baseUrl + "/v2/account/portfolio/history?period=1W&timeframe=15Min",
                HttpMethod.GET,
                entity,
                AlpacaDashboardResponse.PortfolioHistory.class
            );

            // Fetch Positions
            ResponseEntity<AlpacaDashboardResponse.AlpacaPosition[]> positionsResponse = restTemplate.exchange(
                baseUrl + "/v2/positions",
                HttpMethod.GET,
                entity,
                AlpacaDashboardResponse.AlpacaPosition[].class
            );

            System.out.println("Successfully fetched Alpaca data for strategy: " + strategy);
            return new AlpacaDashboardResponse.AlpacaAccountData(
                equity,
                buyingPower,
                historyResponse.getBody(),
                positionsResponse.getBody() != null ? java.util.Arrays.asList(positionsResponse.getBody()) : java.util.Collections.emptyList()
            );
        } catch (Exception e) {
            System.err.println("Error fetching Alpaca data for " + strategy + ": " + e.getMessage());
            e.printStackTrace();
            return null;
        }
    }
}
