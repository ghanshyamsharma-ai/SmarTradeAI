package com.smartraderai.stream;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class StreamApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamApplication.class, args);
    }
}

@RestController
class StreamHealthController {
    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of(
            "status", "ok",
            "service", "spring-boot-stream"
        );
    }
}

@Component
@ConditionalOnProperty(name = "smartraderai.kafka.enabled", havingValue = "true")
class MarketTickConsumer {
    @KafkaListener(topics = "${smartraderai.kafka.topic:smartraderai.market}", groupId = "smartraderai-java")
    public void consume(String payload) {
        // Optional Java consumer hook for live tick processing.
        System.out.println("tick: " + payload);
    }
}
