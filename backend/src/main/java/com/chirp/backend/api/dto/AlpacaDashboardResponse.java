package com.chirp.backend.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public record AlpacaDashboardResponse(
    AlpacaAccountData bullish,
    AlpacaAccountData balanced,
    AlpacaAccountData bearish
) {
    public record AlpacaAccountData(
        Double equity,
        Double buyingPower,
        PortfolioHistory history,
        List<AlpacaPosition> positions
    ) {}

    public record AlpacaPosition(
        @JsonProperty("symbol")
        String symbol,
        @JsonProperty("qty")
        String qty,
        @JsonProperty("market_value")
        String marketValue,
        @JsonProperty("current_price")
        String currentPrice,
        @JsonProperty("change_today")
        String changeToday
    ) {}

    public record PortfolioHistory(
        List<Long> timestamp,
        List<Double> equity,
        @JsonProperty("profit_loss")
        List<Double> profitLoss,
        @JsonProperty("profit_loss_pct")
        List<Double> profitLossPct,
        @JsonProperty("base_value")
        Double baseValue
    ) {}
}
