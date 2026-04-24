package com.chirp.backend.api;

import com.chirp.backend.api.dto.ChirpResponse;
import com.chirp.backend.api.dto.CreateChirpRequest;
import com.chirp.backend.service.InMemoryChirpService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/chirps")
public class ChirpController {
  private final InMemoryChirpService chirpService;

  public ChirpController(InMemoryChirpService chirpService) {
    this.chirpService = chirpService;
  }

  @GetMapping
  public List<ChirpResponse> list() {
    return chirpService.list();
  }

  @PostMapping
  @ResponseStatus(HttpStatus.CREATED)
  public ChirpResponse create(@Valid @RequestBody CreateChirpRequest request) {
    return chirpService.create(request);
  }
}