package com.chirp.backend.api;

import com.chirp.backend.service.StockTwitsService;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/momentum")
public class FeedController {

    private final StockTwitsService stockTwitsService;

    public FeedController(StockTwitsService stockTwitsService) {
        this.stockTwitsService = stockTwitsService;
    }

    @GetMapping(value = "/feed/{ticker}", produces = MediaType.APPLICATION_JSON_VALUE)
    public String getTickerFeed(@PathVariable("ticker") @NotBlank String ticker) {
        return stockTwitsService.getFeedForTicker(ticker);
    }
}