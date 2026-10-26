package dev.triage.lab;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.redis.serializer.SerializationException;
import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class LabTest {
    @Autowired OrderService service;
    @Autowired JdbcTemplate jdbc;
    @Autowired StringRedisTemplate redis;

    private String id() { return "test-" + UUID.randomUUID(); }
    private void stack(Throwable error, String method) {
        assertTrue(java.util.Arrays.stream(error.getStackTrace()).anyMatch(
            f -> f.getClassName().equals(OrderService.class.getName()) && f.getMethodName().equals(method)));
        error.printStackTrace(System.out);
    }

    @Test void scenario1() {
        String id = id();
        stack(assertThrows(NullPointerException.class, () -> service.checkout(id)), "checkout");
        assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM orders WHERE business_no=?", Integer.class, id));
    }
    @Test void scenario2() {
        String id = id();
        try {
            service.create(id);
            stack(assertThrows(DuplicateKeyException.class, () -> service.create(id)), "create");
            assertEquals(1, jdbc.queryForObject("SELECT COUNT(*) FROM orders WHERE business_no=?", Integer.class, id));
        } finally { jdbc.update("DELETE FROM orders WHERE business_no=?", id); }
    }
    @Test void scenario3() {
        String id = id();
        try {
            stack(assertThrows(SerializationException.class, () -> service.cache(id)), "cache");
            assertEquals("{\"customer\":\"Alice\"}", redis.opsForValue().get("order:"+id));
        } finally { redis.delete("order:"+id); }
    }
    @Test void control1() {
        String id = id();
        // Maintainer reference behavior: handle a missing query result explicitly.
        var names = jdbc.queryForList("SELECT customer FROM orders WHERE business_no=?", String.class, id);
        assertTrue(names.isEmpty());
        assertEquals("NOT_FOUND", names.isEmpty() ? "NOT_FOUND" : names.getFirst().toUpperCase());
    }
    @Test void control2() {
        String id = id();
        try {
            jdbc.update("INSERT IGNORE INTO orders(business_no,customer) VALUES (?,?)", id, "Alice");
            jdbc.update("INSERT IGNORE INTO orders(business_no,customer) VALUES (?,?)", id, "Alice");
            assertEquals(1, jdbc.queryForObject("SELECT COUNT(*) FROM orders WHERE business_no=?", Integer.class, id));
        } finally { jdbc.update("DELETE FROM orders WHERE business_no=?", id); }
    }
    @Test void control3() throws Exception {
        String key = "order:"+id();
        try {
            redis.opsForValue().set(key, "{\"customer\":\"Alice\"}");
            var json = new com.fasterxml.jackson.databind.ObjectMapper().readTree(redis.opsForValue().get(key));
            assertEquals("Alice", json.get("customer").asText());
        } finally { redis.delete(key); }
    }
}
