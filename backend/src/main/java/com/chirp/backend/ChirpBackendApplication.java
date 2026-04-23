package com.chirp.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ChirpBackendApplication {
  public static void main(String[] args) {
    SpringApplication.run(ChirpBackendApplication.class, args);
  }
}
