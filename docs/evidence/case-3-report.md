# DevTriage 91b7d2a8e4754060babf7d40d97849ce

状态：reproduced

访问 GET /orders/{id}/cache 时返回 500，日志抛出 org.springframework.data.redis.serializer.SerializationException: Cannot deserialize，根因为 java.io.StreamCorruptedException: invalid stream header: 7B226375，调用链落在 OrderService.cache(OrderService.java:35)。

## 根因

OrderService.cache 中写入与读取使用了不一致的 Redis 序列化方式：第 33 行通过 StringRedisTemplate 以字符串形式写入 JSON 文本 {"customer":"Alice"}，第 35 行却用 JdkSerializationRedisSerializer 对同一 key 的字节做 JDK 原生反序列化。JDK 序列化流要求魔数 AC ED 00 05，而实际字节以 7B 22 63 75（即 {"cu）开头，故 ObjectInputStream.readStreamHeader 抛出 StreamCorruptedException，被包装为 SerializationException。

位置：src/main/java/dev/triage/lab/OrderService.java#cache:33-35

## 修复建议

- 统一序列化方式：既然使用 StringRedisTemplate 写入 JSON 文本，读取时直接返回 raw 字符串（或使用 Jackson2JsonRedisSerializer/ObjectMapper 解析为对象），不要混用 JdkSerializationRedisSerializer。

- 若确需 JDK 序列化，则写入端也必须使用同一 JdkSerializationRedisSerializer（或配置统一的 RedisTemplate<String,Object>），保证写入与读取序列化器一致。

- 清理 Redis 中已存在的旧格式 key（order:*），避免历史数据继续触发反序列化失败。

- 在 cache 方法中对 raw 为 null 的情况做空值判断，避免潜在 NPE，并为反序列化失败增加降级/告警处理。

## 证据缺口

- 日志未包含 correlation id，无法关联具体请求参数与业务单号。

- 未直接观测 Redis 中该 key 的实际存储内容，JSON 格式判断基于异常中的字节头 7B226375 与源码写入逻辑推断。

## 验证

- case-3: reproduced=True, healthy=True; JUnit XML + expected stack + assertions; artifacts=.devtriage\lab\47344cf47c5a; exit=0

## 证据

### 81984ace95640003 @log:1-66

SHA256: d87b89f60ccdc7d3f8a0c33e6e80ff48e3ba346bbe92bc380238bcdf0359156b

```text

app-1  | 2026-10-23T07:03:46.970Z ERROR 1 --- [nio-8080-exec-4] o.a.c.c.C.[.[.[/].[dispatcherServlet]    : Servlet.service() for servlet [dispatcherServlet] in context with path [] threw exception [Request processing failed: org.springframework.data.redis.serializer.SerializationException: Cannot deserialize] with root cause
app-1  | 
app-1  | java.io.StreamCorruptedException: invalid stream header: 7B226375
app-1  | 	at java.base/java.io.ObjectInputStream.readStreamHeader(Unknown Source) ~[na:na]
app-1  | 	at java.base/java.io.ObjectInputStream.<init>(Unknown Source) ~[na:na]
app-1  | 	at org.springframework.core.ConfigurableObjectInputStream.<init>(ConfigurableObjectInputStream.java:65) ~[spring-core-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.core.ConfigurableObjectInputStream.<init>(ConfigurableObjectInputStream.java:51) ~[spring-core-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.core.serializer.DefaultDeserializer.deserialize(DefaultDeserializer.java:69) ~[spring-core-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.core.serializer.support.DeserializingConverter.convert(DeserializingConverter.java:75) ~[spring-core-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.core.serializer.support.DeserializingConverter.convert(DeserializingConverter.java:37) ~[spring-core-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.data.redis.serializer.JdkSerializationRedisSerializer.deserialize(JdkSerializationRedisSerializer.java:111) ~[spring-data-redis-3.5.5.jar!/:3.5.5]
app-1  | 	at dev.triage.lab.OrderService.cache(OrderService.java:35) ~[!/:0.1.0]
app-1  | 	at dev.triage.lab.OrderController.cache(OrderController.java:15) ~[!/:0.1.0]
app-1  | 	at java.base/jdk.internal.reflect.DirectMethodHandleAccessor.invoke(Unknown Source) ~[na:na]
app-1  | 	at java.base/java.lang.reflect.Method.invoke(Unknown Source) ~[na:na]
app-1  | 	at org.springframework.web.method.support.InvocableHandlerMethod.doInvoke(InvocableHandlerMethod.java:258) ~[spring-web-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.web.method.support.InvocableHandlerMethod.invokeForRequest(InvocableHandlerMethod.java:191) ~[spring-web-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.web.servlet.mvc.method.annotation.ServletInvocableHandlerMethod.invokeAndHandle(ServletInvocableHandlerMethod.java:118) ~[spring-webmvc-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter.invokeHandlerMethod(RequestMappingHandlerAdapter.java:991) ~[spring-webmvc-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter.handleInternal(RequestMappingHandlerAdapter.java:896) ~[spring-webmvc-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.web.servlet.mvc.method.AbstractHandlerMethodAdapter.handle(AbstractHandlerMethodAdapter.java:87) ~[spring-webmvc-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.web.servlet.DispatcherServlet.doDispatch(DispatcherServlet.java:1089) ~[spring-webmvc-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.web.servlet.DispatcherServlet.doService(DispatcherServlet.java:979) ~[spring-webmvc-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.web.servlet.FrameworkServlet.processRequest(FrameworkServlet.java:1014) ~[spring-webmvc-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.web.servlet.FrameworkServlet.doGet(FrameworkServlet.java:903) ~[spring-webmvc-6.2.12.jar!/:6.2.12]
app-1  | 	at jakarta.servlet.http.HttpServlet.service(HttpServlet.java:564) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.springframework.web.servlet.FrameworkServlet.service(FrameworkServlet.java:885) ~[spring-webmvc-6.2.12.jar!/:6.2.12]
app-1  | 	at jakarta.servlet.http.HttpServlet.service(HttpServlet.java:658) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.core.ApplicationFilterChain.internalDoFilter(ApplicationFilterChain.java:193) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.core.ApplicationFilterChain.doFilter(ApplicationFilterChain.java:138) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.tomcat.websocket.server.WsFilter.doFilter(WsFilter.java:51) ~[tomcat-embed-websocket-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.core.ApplicationFilterChain.internalDoFilter(ApplicationFilterChain.java:162) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.core.ApplicationFilterChain.doFilter(ApplicationFilterChain.java:138) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.springframework.web.filter.RequestContextFilter.doFilterInternal(RequestContextFilter.java:100) ~[spring-web-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.web.filter.OncePerRequestFilter.doFilter(OncePerRequestFilter.java:116) ~[spring-web-6.2.12.jar!/:6.2.12]
app-1  | 	at org.apache.catalina.core.ApplicationFilterChain.internalDoFilter(ApplicationFilterChain.java:162) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.core.ApplicationFilterChain.doFilter(ApplicationFilterChain.java:138) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.springframework.web.filter.FormContentFilter.doFilterInternal(FormContentFilter.java:93) ~[spring-web-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.web.filter.OncePerRequestFilter.doFilter(OncePerRequestFilter.java:116) ~[spring-web-6.2.12.jar!/:6.2.12]
app-1  | 	at org.apache.catalina.core.ApplicationFilterChain.internalDoFilter(ApplicationFilterChain.java:162) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.core.ApplicationFilterChain.doFilter(ApplicationFilterChain.java:138) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.springframework.web.filter.ServerHttpObservationFilter.doFilterInternal(ServerHttpObservationFilter.java:110) ~[spring-web-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.web.filter.OncePerRequestFilter.doFilter(OncePerRequestFilter.java:116) ~[spring-web-6.2.12.jar!/:6.2.12]
app-1  | 	at org.apache.catalina.core.ApplicationFilterChain.internalDoFilter(ApplicationFilterChain.java:162) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.core.ApplicationFilterChain.doFilter(ApplicationFilterChain.java:138) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.springframework.web.filter.CharacterEncodingFilter.doFilterInternal(CharacterEncodingFilter.java:201) ~[spring-web-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.web.filter.OncePerRequestFilter.doFilter(OncePerRequestFilter.java:116) ~[spring-web-6.2.12.jar!/:6.2.12]
app-1  | 	at org.apache.catalina.core.ApplicationFilterChain.internalDoFilter(ApplicationFilterChain.java:162) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.core.ApplicationFilterChain.doFilter(ApplicationFilterChain.java:138) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.core.StandardWrapperValve.invoke(StandardWrapperValve.java:165) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.core.StandardContextValve.invoke(StandardContextValve.java:88) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.authenticator.AuthenticatorBase.invoke(AuthenticatorBase.java:482) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.core.StandardHostValve.invoke(StandardHostValve.java:113) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.valves.ErrorReportValve.invoke(ErrorReportValve.java:83) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.core.StandardEngineValve.invoke(StandardEngineValve.java:72) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.catalina.connector.CoyoteAdapter.service(CoyoteAdapter.java:342) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.coyote.http11.Http11Processor.service(Http11Processor.java:399) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.coyote.AbstractProcessorLight.process(AbstractProcessorLight.java:63) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.coyote.AbstractProtocol$ConnectionHandler.process(AbstractProtocol.java:903) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.tomcat.util.net.NioEndpoint$SocketProcessor.doRun(NioEndpoint.java:1774) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.tomcat.util.net.SocketProcessorBase.run(SocketProcessorBase.java:52) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.tomcat.util.threads.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:973) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.tomcat.util.threads.ThreadPoolExecutor$Worker.run(ThreadPoolExecutor.java:491) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at org.apache.tomcat.util.threads.TaskThread$WrappingRunnable.run(TaskThread.java:63) ~[tomcat-embed-core-10.1.48.jar!/:na]
app-1  | 	at java.base/java.lang.Thread.run(Unknown Source) ~[na:na]
app-1  | 

```

### 9f1d5621d11c1519 src/main/java/dev/triage/lab/OrderService.java:1-37

SHA256: 345e419ce4befc86985b025c4292f3e9a8509289f914c4b02e46db9366b7c921

```text

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

```

### 2e25da36001e4427 src/main/java/dev/triage/lab/OrderController.java:1-16

SHA256: 0800a34cb1e20f05981478cb6b29a461817e2ceee9b75197970387b229a28b61

```text

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

```