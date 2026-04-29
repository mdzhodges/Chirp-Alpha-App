package com.chirp.backend.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

@Service
public class YahooAuthService {
    private static final Logger log = LoggerFactory.getLogger(YahooAuthService.class);
    // Matching the user's proven User-Agent
    public static final String USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)";

    private final HttpClient httpClient;
    private final CookieManager cookieManager;
    private volatile String crumb;

    public YahooAuthService() {
        this.cookieManager = new CookieManager();
        this.cookieManager.setCookiePolicy(CookiePolicy.ACCEPT_ALL);
        this.httpClient = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NORMAL)
                .cookieHandler(this.cookieManager)
                .build();
    }

    public HttpClient getHttpClient() {
        return httpClient;
    }

    public String getCrumb() {
        if (crumb == null) {
            refresh();
        }
        return crumb;
    }

    public synchronized void refresh() {
        log.warn("Refreshing Yahoo cookie and crumb...");
        try {
            cookieManager.getCookieStore().removeAll();

            // Step 1: Get Cookie (curl -c cookies.txt https://fc.yahoo.com)
            HttpRequest cookieRequest = HttpRequest.newBuilder()
                    .uri(URI.create("https://fc.yahoo.com"))
                    .header("User-Agent", USER_AGENT)
                    .GET()
                    .build();

            httpClient.send(cookieRequest, HttpResponse.BodyHandlers.discarding());
            
            if (cookieManager.getCookieStore().getCookies().isEmpty()) {
                log.error("No cookies captured from fc.yahoo.com");
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Failed to obtain Yahoo auth cookies");
            }

            // Step 2: Get Crumb (curl -b cookies.txt https://query2.finance.yahoo.com/v1/test/getcrumb)
            HttpRequest crumbRequest = HttpRequest.newBuilder()
                    .uri(URI.create("https://query2.finance.yahoo.com/v1/test/getcrumb"))
                    .header("User-Agent", USER_AGENT)
                    .GET()
                    .build();

            HttpResponse<String> crumbResponse = httpClient.send(crumbRequest, HttpResponse.BodyHandlers.ofString());
            if (crumbResponse.statusCode() != 200) {
                log.error("Failed to get Yahoo crumb. Status: {}, Body: {}", crumbResponse.statusCode(), crumbResponse.body());
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Failed to obtain Yahoo crumb (Status: " + crumbResponse.statusCode() + ")");
            }

            this.crumb = crumbResponse.body().trim();
            log.info("Successfully refreshed Yahoo auth. Crumb: {}", this.crumb);
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            log.error("Error during Yahoo auth refresh", e);
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Failed to refresh Yahoo authentication", e);
        }
    }

    public void invalidate() {
        this.crumb = null;
    }
}
