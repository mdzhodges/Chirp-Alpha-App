package com.chirp.backend.api.dto;

import java.time.Instant;

public record ChirpResponse(long id, String message, String author, Instant createdAt) {}

