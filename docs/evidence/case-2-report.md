# DevTriage e9cd86ea82624e8dae88d6070ddca3bc

状态：reproduced

调用 POST /orders/{id} 创建订单时返回 500，日志抛出 org.springframework.dao.DuplicateKeyException，根因为 java.sql.SQLIntegrityConstraintViolationException: Duplicate entry 'incident-23100e614736' for key 'orders.business_no'，SQL 为 INSERT INTO orders(business_no, customer) VALUES (?, ?)。

## 根因

OrderService.create 无条件执行 INSERT，未先校验 business_no 是否已存在，也未使用幂等或 upsert 语义；而 schema.sql 中 orders.business_no 定义为 NOT NULL UNIQUE，因此对同一业务号重复提交（重试或重复请求）时数据库拒绝插入，MySQL 驱动抛出唯一键冲突，Spring 将其翻译为 DuplicateKeyException 并冒泡到 OrderController.create，最终由 DispatcherServlet 以 500 返回。

位置：src/main/java/dev/triage/lab/OrderService.java#create:27-29

## 修复建议

- 在 OrderService.create 中先按 business_no 查询，存在则返回既有记录或抛出业务异常（如 409 Conflict），避免直接 INSERT。

- 改用幂等写入：INSERT ... ON DUPLICATE KEY UPDATE 或 INSERT IGNORE，并明确业务语义。

- 在 OrderController 增加 @ExceptionHandler 将 DuplicateKeyException 映射为 409 而非 500，避免异常栈污染日志。

- 若业务号由客户端生成，改为服务端生成唯一业务号或引入幂等键（Idempotency-Key）机制。

- 为 create 补充并发或重复提交的回归测试，覆盖唯一约束冲突路径。

## 证据缺口

- 日志中无 correlation id 与请求上下文，无法确认重复提交是客户端重试还是并发双写。

- 未获取数据库侧审计记录，无法确认首次插入的时间与来源。

## 验证

- case-2: reproduced=True, healthy=True; JUnit XML + expected stack + assertions; artifacts=.devtriage\lab\bc0164a57a7a; exit=0

## 证据

### e7ff1130bf493135 @log:1-72

SHA256: a80c7a6e48867ca79b545698b22319a5701067ca21963a4322db9c2ea386f7fc

```text

app-1  | 2026-10-23T07:03:45.122Z ERROR 1 --- [nio-8080-exec-3] o.a.c.c.C.[.[.[/].[dispatcherServlet]    : Servlet.service() for servlet [dispatcherServlet] in context with path [] threw exception [Request processing failed: org.springframework.dao.DuplicateKeyException: PreparedStatementCallback; SQL [INSERT INTO orders(business_no, customer) VALUES (?, ?)]; Duplicate entry 'incident-23100e614736' for key 'orders.business_no'] with root cause
app-1  | 
app-1  | java.sql.SQLIntegrityConstraintViolationException: Duplicate entry 'incident-23100e614736' for key 'orders.business_no'
app-1  | 	at com.mysql.cj.jdbc.exceptions.SQLError.createSQLException(SQLError.java:109) ~[mysql-connector-j-9.4.0.jar!/:9.4.0]
app-1  | 	at com.mysql.cj.jdbc.exceptions.SQLExceptionsMapping.translateException(SQLExceptionsMapping.java:114) ~[mysql-connector-j-9.4.0.jar!/:9.4.0]
app-1  | 	at com.mysql.cj.jdbc.ClientPreparedStatement.executeInternal(ClientPreparedStatement.java:988) ~[mysql-connector-j-9.4.0.jar!/:9.4.0]
app-1  | 	at com.mysql.cj.jdbc.ClientPreparedStatement.executeUpdateInternal(ClientPreparedStatement.java:1166) ~[mysql-connector-j-9.4.0.jar!/:9.4.0]
app-1  | 	at com.mysql.cj.jdbc.ClientPreparedStatement.executeUpdateInternal(ClientPreparedStatement.java:1101) ~[mysql-connector-j-9.4.0.jar!/:9.4.0]
app-1  | 	at com.mysql.cj.jdbc.ClientPreparedStatement.executeLargeUpdate(ClientPreparedStatement.java:1448) ~[mysql-connector-j-9.4.0.jar!/:9.4.0]
app-1  | 	at com.mysql.cj.jdbc.ClientPreparedStatement.executeUpdate(ClientPreparedStatement.java:1084) ~[mysql-connector-j-9.4.0.jar!/:9.4.0]
app-1  | 	at com.zaxxer.hikari.pool.ProxyPreparedStatement.executeUpdate(ProxyPreparedStatement.java:61) ~[HikariCP-6.3.3.jar!/:na]
app-1  | 	at com.zaxxer.hikari.pool.HikariProxyPreparedStatement.executeUpdate(HikariProxyPreparedStatement.java) ~[HikariCP-6.3.3.jar!/:na]
app-1  | 	at org.springframework.jdbc.core.JdbcTemplate.lambda$update$2(JdbcTemplate.java:977) ~[spring-jdbc-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.jdbc.core.JdbcTemplate.execute(JdbcTemplate.java:658) ~[spring-jdbc-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.jdbc.core.JdbcTemplate.update(JdbcTemplate.java:972) ~[spring-jdbc-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.jdbc.core.JdbcTemplate.update(JdbcTemplate.java:1016) ~[spring-jdbc-6.2.12.jar!/:6.2.12]
app-1  | 	at org.springframework.jdbc.core.JdbcTemplate.update(JdbcTemplate.java:1026) ~[spring-jdbc-6.2.12.jar!/:6.2.12]
app-1  | 	at dev.triage.lab.OrderService.create(OrderService.java:28) ~[!/:0.1.0]
app-1  | 	at dev.triage.lab.OrderController.create(OrderController.java:13) ~[!/:0.1.0]
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
app-1  | 	at org.springframework.web.servlet.FrameworkServlet.doPost(FrameworkServlet.java:914) ~[spring-webmvc-6.2.12.jar!/:6.2.12]
app-1  | 	at jakarta.servlet.http.HttpServlet.service(HttpServlet.java:590) ~[tomcat-embed-core-10.1.48.jar!/:na]
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

### 24919265a655f9e5 src/main/resources/schema.sql:1-5

SHA256: 2a65e9f78ddad9b9d624322eeef6d0e838236f5c0e6a68ba3df5fb440dd5d102

```text

CREATE TABLE IF NOT EXISTS orders (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  business_no VARCHAR(100) NOT NULL UNIQUE,
  customer VARCHAR(100) NOT NULL
);

```