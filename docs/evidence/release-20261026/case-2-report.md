# DevTriage 9b4b49180bb1402c8b2b800743e338fb

状态：reproduced

POST /orders/{id} 创建订单时抛出 org.springframework.dao.DuplicateKeyException，底层为 java.sql.SQLIntegrityConstraintViolationException: Duplicate entry 'incident-5986e0be041c' for key 'orders.business_no'，请求返回 500。

## 根因

OrderService.create 直接执行 INSERT INTO orders(business_no, customer)，而 orders.business_no 在 schema.sql 中定义为 NOT NULL UNIQUE；当同一 business_no（如 incident-5986e0be041c）被重复提交时，数据库唯一约束冲突被 Spring 翻译为 DuplicateKeyException。代码中没有任何幂等/去重或冲突处理（未先查询、未使用 INSERT ... ON DUPLICATE KEY UPDATE / INSERT IGNORE，也未捕获 DuplicateKeyException 转为幂等成功或 409），因此重复请求必然以 500 失败。

位置：src/main/java/dev/triage/lab/OrderService.java#create:26-29

## 修复建议

- 在 OrderService.create 中实现幂等：先按 business_no 查询，存在则直接返回；或使用 INSERT ... ON DUPLICATE KEY UPDATE / INSERT IGNORE 并检查影响行数。

- 捕获 DuplicateKeyException 并转换为业务语义（幂等成功或 HTTP 409 Conflict），避免以 500 暴露给调用方。

- 在 Controller 层对 business_no 做请求级去重/幂等键校验（如 Idempotency-Key），并补充重复提交的单元/集成测试。

- 确认上游是否因重试或重复投递导致同一 business_no 多次提交，检查调用方重试策略与消息去重。

## 证据缺口

- 缺少数据库会话/实际表数据快照，无法确认该 business_no 是首次插入还是重复提交（仅由唯一约束冲突推断）。

- 缺少应用运行时指标（请求量、重试次数、上游调用方信息）与部署变更记录，无法判断重复提交的触发来源。

- 未检索到与该 DuplicateKey 场景匹配的历史知识条目（唯一命中为 Redis 缓存击穿文档，与本次问题无关）。

## 验证

- case-2: reproduced=True, healthy=True; JUnit XML + expected stack + assertions; artifacts=.devtriage\lab\eac50093a01e; exit=0

## 证据

### de8bf21520642343 @log:1-72

SHA256: 3ee6218b45ddb8a57025c4f9d07ab70bf8ff2992b7ad4abe37d74085f5d7f5a9

```text

app-1  | 2026-10-26T06:03:15.725Z ERROR 1 --- [nio-8080-exec-3] o.a.c.c.C.[.[.[/].[dispatcherServlet]    : Servlet.service() for servlet [dispatcherServlet] in context with path [] threw exception [Request processing failed: org.springframework.dao.DuplicateKeyException: PreparedStatementCallback; SQL [INSERT INTO orders(business_no, customer) VALUES (?, ?)]; Duplicate entry 'incident-5986e0be041c' for key 'orders.business_no'] with root cause
app-1  | 
app-1  | java.sql.SQLIntegrityConstraintViolationException: Duplicate entry 'incident-5986e0be041c' for key 'orders.business_no'
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

### c1bc20566d61f957 src/main/java/dev/triage/lab/OrderService.java:28-28

SHA256: 345e419ce4befc86985b025c4292f3e9a8509289f914c4b02e46db9366b7c921

```text

        jdbc.update("INSERT INTO orders(business_no, customer) VALUES (?, ?)", businessNo, "Alice");

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

### 7b38962fa50d403a src/main/resources/schema.sql:3-3

SHA256: 2a65e9f78ddad9b9d624322eeef6d0e838236f5c0e6a68ba3df5fb440dd5d102

```text

  business_no VARCHAR(100) NOT NULL UNIQUE,

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

## 历史知识参考（不代表当前故障已验证）