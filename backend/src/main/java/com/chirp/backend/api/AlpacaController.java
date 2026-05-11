package com.chirp.backend.api;

import com.chirp.backend.api.dto.AlpacaDashboardResponse;
import com.chirp.backend.service.AlpacaService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/alpaca")
public class AlpacaController {

    private final AlpacaService alpacaService;

    public AlpacaController(AlpacaService alpacaService) {
        this.alpacaService = alpacaService;
    }

    @GetMapping("/dashboard")
    public AlpacaDashboardResponse getDashboardData() {
        return alpacaService.getDashboardData();
    }
}
