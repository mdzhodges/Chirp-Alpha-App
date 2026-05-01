package com.chirp.backend.api.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record TickerRequest(@NotBlank @Size(min = 1, max = 64) String symbol, String modelType) {}

