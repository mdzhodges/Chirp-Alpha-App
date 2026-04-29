package com.chirp.backend.api.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record TickerResponse(
    String symbol,
    String name,
    String currency,
    String exchange,
    BigDecimal price,
    BigDecimal change,
    BigDecimal changePercent,
    BigDecimal open,
    BigDecimal previousClose,
    BigDecimal dayHigh,
    BigDecimal dayLow,
    Long volume,
    Long avgVolume,
    BigDecimal marketCap,
    BigDecimal pe,
    BigDecimal forwardPE,
    BigDecimal eps,
    BigDecimal dividendYield,
    BigDecimal beta,
    BigDecimal priceToBook,
    BigDecimal profitMargins,
    BigDecimal enterpriseValue,
    Long sharesOutstanding,
    BigDecimal yearHigh,
    BigDecimal yearLow,
    BigDecimal momentum,
    List<MomentumPoint> momentumHistory,
    List<GraphPoint> graphData,
    Instant fetchedAt) {

  public record GraphPoint(
      Instant timestamp,
      BigDecimal open,
      BigDecimal high,
      BigDecimal low,
      BigDecimal close) {}

  public record MomentumPoint(
      Instant timestamp,
      BigDecimal value) {}
}

