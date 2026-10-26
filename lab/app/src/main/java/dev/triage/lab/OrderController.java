package dev.triage.lab;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService service;
    public OrderController(OrderService service) { this.service = service; }
    @GetMapping("/{id}")
    public String checkout(@PathVariable String id) { return service.checkout(id); }
    @PostMapping("/{id}")
    public void create(@PathVariable String id) { service.create(id); }
    @GetMapping("/{id}/cache")
    public Object cache(@PathVariable String id) { return service.cache(id); }
}
