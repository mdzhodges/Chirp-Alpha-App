package com.chirp.backend.service;

import com.chirp.backend.api.dto.ChirpResponse;
import com.chirp.backend.api.dto.CreateChirpRequest;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class InMemoryChirpService {
  private final AtomicLong idSequence = new AtomicLong(0);
  private final CopyOnWriteArrayList<ChirpResponse> chirps = new CopyOnWriteArrayList<>();

  public List<ChirpResponse> list() {
    ArrayList<ChirpResponse> copy = new ArrayList<>(chirps);
    copy.sort(Comparator.comparing(ChirpResponse::createdAt).reversed());
    return copy;
  }

  public ChirpResponse create(CreateChirpRequest request) {
    long id = idSequence.incrementAndGet();
    String author = (request.author() == null || request.author().isBlank()) ? "anonymous" : request.author().trim();
    ChirpResponse chirp = new ChirpResponse(id, request.message().trim(), author, Instant.now());
    chirps.add(chirp);
    return chirp;
  }
}

