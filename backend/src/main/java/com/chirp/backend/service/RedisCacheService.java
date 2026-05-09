package com.chirp.backend.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.Optional;
import java.util.function.Supplier;

@Service
public class RedisCacheService {
    private static final Logger log = LoggerFactory.getLogger(RedisCacheService.class);

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final boolean enabled;
    private final boolean logOps;
    private final Duration outageBackoff;
    private volatile long disabledUntilEpochMs = 0L;

    public RedisCacheService(
            StringRedisTemplate redisTemplate,
            ObjectMapper objectMapper,
            @Value("${cache.redis.enabled:true}") boolean enabled,
            @Value("${cache.redis.log-ops:false}") boolean logOps,
            @Value("${cache.redis.outage-backoff:PT5M}") Duration outageBackoff) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
        this.enabled = enabled;
        this.logOps = logOps;
        this.outageBackoff = outageBackoff;
    }

    public <T> Optional<T> get(String key, Class<T> type) {
        if (!enabled || isTemporarilyDisabled()) {
            return Optional.empty();
        }

        try {
            String payload = redisTemplate.opsForValue().get(key);
            if (payload == null || payload.isBlank()) {
                if (logOps) {
                    log.info("Redis cache miss: {}", key);
                }
                return Optional.empty();
            }

            if (logOps) {
                log.info("Redis cache hit: {}", key);
            }
            return Optional.of(objectMapper.readValue(payload, type));
        } catch (Exception e) {
            log.warn("Redis cache read failed for key {}: {}", key, e.getMessage());
            markUnavailable();
            return Optional.empty();
        }
    }

    public void put(String key, Object value, Duration ttl) {
        if (!enabled || isTemporarilyDisabled() || value == null || ttl == null || ttl.isZero() || ttl.isNegative()) {
            return;
        }

        try {
            redisTemplate.opsForValue().set(key, objectMapper.writeValueAsString(value), ttl);
            if (logOps) {
                log.info("Redis cache write: {} (ttl={})", key, ttl);
            }
        } catch (Exception e) {
            log.warn("Redis cache write failed for key {}: {}", key, e.getMessage());
            markUnavailable();
        }
    }

    public <T> T getOrCompute(String key, Class<T> type, Duration ttl, Supplier<T> loader) {
        Optional<T> cached = get(key, type);
        if (cached.isPresent()) {
            return cached.get();
        }

        T value = loader.get();
        put(key, value, ttl);
        return value;
    }

    private boolean isTemporarilyDisabled() {
        return System.currentTimeMillis() < disabledUntilEpochMs;
    }

    private void markUnavailable() {
        long backoffMillis = outageBackoff == null ? Duration.ofMinutes(5).toMillis() : outageBackoff.toMillis();
        disabledUntilEpochMs = System.currentTimeMillis() + Math.max(backoffMillis, 0L);
    }
}
