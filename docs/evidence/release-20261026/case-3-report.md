# DevTriage 230e1e9db9a54e88b7c297fcd5fe1af4

状态：reproduced

GET /orders/{id}/cache 请求返回 500，日志报 org.springframework.data.redis.serializer.SerializationException: Cannot deserialize，根因 java.io.StreamCorruptedException: invalid stream header: 7B226375，异常栈定位到 dev.triage.lab.OrderService.cache(OrderService.java:35)。

## 根因

OrderService.cache 使用 StringRedisTemplate 以纯文本 JSON（{"customer":"Alice"}）写入 Redis，但读取时用 new JdkSerializationRedisSerializer().deserialize(raw.getBytes(UTF_8)) 按 JDK 二进制序列化格式解析。JDK 反序列化要求流头 0xACED，而实际字节为 7B 22 63 75（即 '{"cu'），ObjectInputStream.readStreamHeader 因此抛出 StreamCorruptedException，被包装成 SerializationException。即写入端与读取端序列化器不一致（String/JSON vs JDK 序列化）。

位置：src/main/java/dev/triage/lab/OrderService.java#cache:30-36

## 修复建议

- 统一序列化方式：若值以 JSON 文本写入，读取时直接使用 StringRedisTemplate.opsForValue().get(key) 返回 String，再用 Jackson 反序列化为对象，不要使用 JdkSerializationRedisSerializer。

- 若确实需要 JDK 序列化，则写入端也必须用同一 JdkSerializationRedisSerializer 序列化对象（set 时传 byte[]），保证读写序列化器一致。

- 为 RedisTemplate 显式配置 key/value 序列化器（如 StringRedisSerializer + GenericJackson2JsonRedisSerializer），避免默认 JDK 序列化与 String 模板混用。

- 对缓存读取做容错：捕获 SerializationException 视为缓存未命中并回源重建，同时清理脏 key（order:{id}）。

- 排查历史脏数据：确认 order:* 键是否由旧版本/其他服务以不同格式写入，必要时批量清理或迁移。

## 证据缺口

- 无 Redis 运行时观测（键的实际类型、TTL、写入方），无法确认脏数据来源与影响范围。

- 无应用指标/链路追踪数据，无法评估该错误的发生频率与影响面。

- 未检索到可用的历史知识库条目（search_knowledge 返回空）。

## 验证

- case-3: reproduced=True, healthy=True; JUnit XML + expected stack + assertions; artifacts=.devtriage\lab\8e533aab3587; exit=0

## 证据

### a9488bf75e4d3866 @log:1-66

SHA256: 454a43fd417e6c99a1e4a94e5aea8baba944cd25bdfbaf6465fee653f6f2aa6a

```text

app-1  | 2026-10-26T06:03:15.933Z ERROR 1 --- [nio-8080-exec-4] o.a.c.c.C.[.[.[/].[dispatcherServlet]    : Servlet.service() for servlet [dispatcherServlet] in context with path [] threw exception [Request processing failed: org.springframework.data.redis.serializer.SerializationException: Cannot deserialize] with root cause
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

### ea612392b7ae9d3a pom.xml:1-17

SHA256: 6a8b78c75472c044fab9c4aae0e88bb0fc06d16b6336bbfd066a18b20202a929

```text

<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.5.7</version><relativePath/></parent>
  <groupId>dev.triage</groupId><artifactId>order-lab</artifactId><version>0.1.0</version>
  <properties><java.version>21</java.version><lab.build.dir>${project.basedir}/target</lab.build.dir></properties>
  <dependencies>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-actuator</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-jdbc</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-data-redis</artifactId></dependency>
    <dependency><groupId>com.mysql</groupId><artifactId>mysql-connector-j</artifactId><scope>runtime</scope></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-test</artifactId><scope>test</scope></dependency>
  </dependencies>
  <build><directory>${lab.build.dir}</directory><plugins>
    <plugin><groupId>org.springframework.boot</groupId><artifactId>spring-boot-maven-plugin</artifactId></plugin>
  </plugins></build>
</project>

```

## 历史知识参考（不代表当前故障已验证）