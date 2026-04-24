package com.chirp.backend.service;

import com.chirp.backend.api.dto.TickerResponse;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.math.BigDecimal;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AlphaVantageTickerService {
  private static final ZoneId MARKET_TIME_ZONE = ZoneId.of("America/New_York");
  private static final DateTimeFormatter TIMESTAMP_FORMAT =
      DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

  private final HttpClient httpClient;
  private final ObjectMapper objectMapper;

  public AlphaVantageTickerService(ObjectMapper objectMapper) {
    this.httpClient = HttpClient.newHttpClient();
    this.objectMapper = objectMapper;
  }

  public TickerResponse fetch(String symbol) {
    String normalized = normalizeSymbol(symbol);
    String apiKey = resolveApiKey();

    URI uri = buildDailyUri(normalized, apiKey);
    String body = httpGet(uri);

    JsonNode root;
    try {
      root = objectMapper.readTree(body);
    } catch (IOException e) {
      throw new ResponseStatusException(
          HttpStatus.BAD_GATEWAY, "Invalid response from Alpha Vantage", e);
    }

    String apiError = extractAlphaVantageError(root);
    if (apiError != null) {
      throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, apiError);
    }

    JsonNode meta = root.get("Meta Data");
    JsonNode series = root.get("Time Series (Daily)");
    if (meta == null || series == null || !series.isObject()) {
      throw new ResponseStatusException(
          HttpStatus.BAD_GATEWAY, "Alpha Vantage response missing daily time series data");
    }

    List<DailyPoint> points = parseSeries(series);
    if (points.isEmpty()) {
      throw new ResponseStatusException(
          HttpStatus.NOT_FOUND, "No daily data available for symbol: " + normalized);
    }

    points.sort(Comparator.comparing(p -> p.timestamp));
    DailyPoint latest = points.get(points.size() - 1);
    DailyPoint previous = points.size() >= 2 ? points.get(points.size() - 2) : null;

    BigDecimal dayHigh = latest.high;
    BigDecimal dayLow = latest.low;
    Long dayVolume = latest.volume;

    BigDecimal price = latest.close;
    BigDecimal change = previous == null ? null : price.subtract(previous.close);
    BigDecimal changePercent =
        previous == null || previous.close == null || previous.close.compareTo(BigDecimal.ZERO) == 0
            ? null
            : change.multiply(BigDecimal.valueOf(100)).divide(previous.close, 6, RoundingMode.HALF_UP);

    String currency = "USD";
    String exchange = null;
    String name = null;

    return new TickerResponse(
        normalized,
        name,
        currency,
        exchange,
        price,
        change,
        changePercent,
        latest.open,
        previous == null ? null : previous.close,
        dayHigh,
        dayLow,
        dayVolume,
        null,
        null,
        null,
        null,
        null,
        null,
        Instant.now());
  }

  private static String normalizeSymbol(String symbol) {
    if (symbol == null || symbol.isBlank()) {
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "symbol is required");
    }
    return symbol.trim().toUpperCase();
  }

  private static URI buildDailyUri(String symbol, String apiKey) {
    String query =
        "function=TIME_SERIES_DAILY"
            + "&symbol="
            + urlEncode(symbol)
            + "&outputsize=compact"
            + "&datatype=json"
            + "&apikey="
            + urlEncode(apiKey);

    return URI.create("https://www.alphavantage.co/query?" + query);
  }

  private String httpGet(URI uri) {
    HttpRequest request =
        HttpRequest.newBuilder()
            .uri(uri)
            .GET()
            .header("accept", "application/json")
            .build();

    HttpResponse<String> response;
    try {
      response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Request to Alpha Vantage was interrupted", e);
    } catch (IOException e) {
      throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Failed to reach Alpha Vantage", e);
    }

    if (response.statusCode() < 200 || response.statusCode() >= 300) {
      throw new ResponseStatusException(
          HttpStatus.BAD_GATEWAY, "Alpha Vantage request failed (" + response.statusCode() + ")");
    }
    return response.body();
  }

  private static List<DailyPoint> parseSeries(JsonNode series) {
    Map<String, DailyPoint> points = new HashMap<>();
    series.fields()
        .forEachRemaining(
            entry -> {
              Instant timestamp = parseAlphaTimestamp(entry.getKey());
              JsonNode values = entry.getValue();
              if (timestamp == null || values == null || !values.isObject()) return;

              BigDecimal open = parseDecimal(values.get("1. open"));
              BigDecimal high = parseDecimal(values.get("2. high"));
              BigDecimal low = parseDecimal(values.get("3. low"));
              BigDecimal close = parseDecimal(values.get("4. close"));
              Long volume = parseLong(values.get("5. volume"));
              if (open == null || high == null || low == null || close == null) return;

              points.put(entry.getKey(), new DailyPoint(timestamp, open, high, low, close, volume));
            });

    return new ArrayList<>(points.values());
  }

  private static Instant parseAlphaTimestamp(String timestamp) {
    if (timestamp == null || timestamp.isBlank()) return null;
    try {
      LocalDate localDate = LocalDate.parse(timestamp, DateTimeFormatter.ISO_LOCAL_DATE);
      return localDate.atStartOfDay(MARKET_TIME_ZONE).toInstant();
    } catch (DateTimeParseException ignored) {
    }

    try {
      return OffsetDateTime.parse(timestamp).toInstant();
    } catch (DateTimeParseException ignored) {
    }

    try {
      LocalDateTime localDateTime = LocalDateTime.parse(timestamp, TIMESTAMP_FORMAT);
      return localDateTime.atZone(MARKET_TIME_ZONE).toInstant();
    } catch (DateTimeParseException ignored) {
      return null;
    }
  }

  private static BigDecimal parseDecimal(JsonNode node) {
    if (node == null || node.isNull()) return null;
    String text = node.asText(null);
    if (text == null || text.isBlank()) return null;
    try {
      return new BigDecimal(text);
    } catch (NumberFormatException e) {
      return null;
    }
  }

  private static Long parseLong(JsonNode node) {
    if (node == null || node.isNull()) return null;
    String text = node.asText(null);
    if (text == null || text.isBlank()) return null;
    try {
      return Long.parseLong(text);
    } catch (NumberFormatException e) {
      return null;
    }
  }

  private static String extractAlphaVantageError(JsonNode root) {
    if (root == null || !root.isObject()) return "Invalid response from Alpha Vantage";
    JsonNode error = root.get("Error Message");
    if (error != null && !error.isNull() && !error.asText("").isBlank()) {
      return error.asText();
    }
    JsonNode note = root.get("Note");
    if (note != null && !note.isNull() && !note.asText("").isBlank()) {
      return note.asText();
    }
    JsonNode info = root.get("Information");
    if (info != null && !info.isNull() && !info.asText("").isBlank()) {
      return info.asText();
    }
    return null;
  }

  private String resolveApiKey() {
    String direct = System.getenv("ALPHA_VANTAGE_API_KEY");
    if (direct != null && !direct.isBlank()) return direct.trim();

    String fromEnvFile = readDotEnvKey("ALPHA_VANTAGE_API_KEY");
    if (fromEnvFile != null && !fromEnvFile.isBlank()) return fromEnvFile.trim();

    throw new ResponseStatusException(
        HttpStatus.INTERNAL_SERVER_ERROR,
        "ALPHA_VANTAGE_API_KEY is not configured (set env var or add it to root .env)");
  }

  private static String readDotEnvKey(String key) {
    for (Path path : new Path[] {Path.of(".env"), Path.of("../.env"), Path.of("../../.env")}) {
      String value = tryReadDotEnvValue(path, key);
      if (value != null) return value;
    }
    return null;
  }

  private static String tryReadDotEnvValue(Path path, String key) {
    if (path == null || !Files.exists(path)) return null;
    List<String> lines;
    try {
      lines = Files.readAllLines(path);
    } catch (IOException e) {
      return null;
    }

    for (String raw : lines) {
      if (raw == null) continue;
      String line = raw.trim();
      if (line.isEmpty() || line.startsWith("#")) continue;
      int idx = line.indexOf('=');
      if (idx <= 0) continue;
      String k = line.substring(0, idx).trim();
      if (!key.equals(k)) continue;
      String v = line.substring(idx + 1).trim();
      if ((v.startsWith("\"") && v.endsWith("\"")) || (v.startsWith("'") && v.endsWith("'"))) {
        v = v.substring(1, v.length() - 1);
      }
      return v;
    }
    return null;
  }

  private static String urlEncode(String value) {
    return URLEncoder.encode(value, StandardCharsets.UTF_8);
  }

  private record DailyPoint(
      Instant timestamp, BigDecimal open, BigDecimal high, BigDecimal low, BigDecimal close, Long volume) {}
}
