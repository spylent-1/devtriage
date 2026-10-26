package dev.triage.lab;

import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final JdbcTemplate jdbc;
    private final StringRedisTemplate redis;

    public OrderService(JdbcTemplate jdbc, StringRedisTemplate redis) {
        this.jdbc = jdbc;
        this.redis = redis;
    }

    public String checkout(String businessNo) {
        List<String> names = jdbc.queryForList(
            "SELECT customer FROM orders WHERE business_no = ?", String.class, businessNo);
        String customer = names.isEmpty() ? null : names.getFirst();
        return customer.toUpperCase();
    }

    public void create(String businessNo) {
        jdbc.update("INSERT INTO orders(business_no, customer) VALUES (?, ?)", businessNo, "Alice");
    }

    public Object cache(String businessNo) {
        String key = "order:" + businessNo;
        redis.opsForValue().set(key, "{\"customer\":\"Alice\"}");
        String raw = redis.opsForValue().get(key);
        return new JdkSerializationRedisSerializer().deserialize(raw.getBytes(StandardCharsets.UTF_8));
    }
}
