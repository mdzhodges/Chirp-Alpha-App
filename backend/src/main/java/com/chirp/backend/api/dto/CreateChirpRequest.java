package com.chirp.backend.api.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateChirpRequest(
    @NotBlank @Size(min = 1, max = 280) String message,
    @Size(max = 64) String author
) {}

