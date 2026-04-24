package com.chirp.backend.api.dto;

import java.math.BigDecimal;
import java.time.Instant;

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
    BigDecimal eps,
    BigDecimal yearHigh,
    BigDecimal yearLow,
    Instant fetchedAt) {}

