package com.chirp.backend.api;

import com.chirp.backend.api.dto.TickerRequest;
import com.chirp.backend.api.dto.TickerResponse;
import com.chirp.backend.service.AlphaVantageTickerService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/ticker")
public class TickerController {
  private final AlphaVantageTickerService tickerService;

  public TickerController(AlphaVantageTickerService tickerService) {
    this.tickerService = tickerService;
  }

  @GetMapping
  public TickerResponse fetchByQuery(
      @RequestParam("symbol") @NotBlank @Size(min = 1, max = 64) String symbol) {
    return tickerService.fetch(symbol);
  }

  @GetMapping("/{symbol}")
  public TickerResponse fetchByPath(@PathVariable("symbol") @NotBlank @Size(min = 1, max = 64) String symbol) {
    return tickerService.fetch(symbol);
  }

  @PostMapping
  public TickerResponse fetchByBody(@Valid @RequestBody TickerRequest request) {
    return tickerService.fetch(request.symbol());
  }
}
