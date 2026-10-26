# DevTriage 68c93cecd2e646b2b10a5b6841fd3e17

状态：insufficient

checkout 调用在获取数据库连接时抛出 java.sql.SQLTransientConnectionException：HikariPool-1 - Connection is not available, request timed out after 30000ms，即请求等待连接池 30 秒后超时。

## 根因

日志显示连接获取阶段（HikariPool.getConnection）在 30 秒后超时，调用点位于 OrderService.checkout 第 12 行的 pool.getConnection()。源码中 checkout 使用 try-with-resources 获取并关闭连接，本身未见明显泄漏路径，但仓库内不存在任何 Hikari/DataSource 配置（无 hikari、maximumPoolSize、datasource 相关配置项），因此无法判定是池容量不足、慢 SQL/长事务占用、连接泄漏还是数据库不可达。当前证据只能支持“连接池获取连接超时”这一现象，根因类别无法确定。

位置：OrderService.java:demo.OrderService.checkout:12-15

## 修复建议

- 采集运行时证据：HikariCP 指标（active/idle/pending/total 连接数、等待队列长度、连接获取耗时分布），确认是池耗尽还是数据库侧不可达。

- 抓取超时时刻的线程栈（jstack），定位是否有线程长时间持有连接（长事务/慢 SQL）或借出未归还的调用路径。

- 在数据库侧检查活动会话、锁等待与慢查询日志，确认是否存在慢 SQL 或长事务占用连接。

- 独立验证数据库网络连通性与认证（连接串、账号、防火墙），排除数据库不可达。

- 补齐并审查连接池配置（maximumPoolSize、connectionTimeout、leakDetectionThreshold、maxLifetime），在确认根因前不要盲目增大池大小。

- 为 checkout 增加超时/重试与降级策略，并对连接获取失败打点告警，附带 traceId 便于关联。

## 证据缺口

- 缺少 HikariCP/DataSource 配置（仓库内无 hikari、maximumPoolSize、datasource 相关配置），无法判断池容量与超时参数。

- 缺少运行时指标：active/idle/pending 连接数、等待队列、连接获取耗时。

- 缺少数据库侧证据：活动会话、锁等待、慢 SQL 日志。

- 缺少线程栈，无法判断是否存在长事务或连接泄漏。

- 日志无时间戳与 correlation id，无法关联并发量与故障时段。

- 未执行任何实验验证（verify=none），无法复现。

## 验证

## 证据

### fd339c77792de417 @log:1-3

SHA256: 31c9656a91084a9802a42ab1853f1acb0b644f4d7a0c46a27b67600595636062

```text

java.sql.SQLTransientConnectionException: HikariPool-1 - Connection is not available, request timed out after 30000ms.
 at com.zaxxer.hikari.pool.HikariPool.getConnection(HikariPool.java:200)
 at demo.OrderService.checkout(OrderService.java:12)

```

### c2a936dc6f7a982d OrderService.java:1-16

SHA256: 836e8db6bfc4ef8f50866b761ad5d130e88b337ed3453ad33cec54853cf36217

```text

package demo;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

// Synthetic diagnostic input; this directory is not a deployable application.
public class OrderService {
    private final DataSource pool;
    public OrderService(DataSource pool) { this.pool = pool; }
    public void checkout() throws SQLException {
        try (Connection connection = pool.getConnection()) {
            connection.createStatement().execute("SELECT 1");
        }
    }
}

```

## 历史知识参考（不代表当前故障已验证）

### kb-e57876f196c183b0453fa898 HikariCP 获取连接超时排查

来源：curated://devtriage/hikari-timeout；版本：1；行：1-7

SHA256: f106a455573ee00197c8df1a11185ba22cd03a3341445d29337239bba3bee303

```text

适用：HikariCP 连接池。此文为排障指南，不能替代运行时证据。
症状：Connection is not available, request timed out；数据库连接池耗尽，请求等待获取连接。
先收集 active、idle、pending 连接数、数据库活动会话、慢 SQL 和线程栈。
候选原因：慢 SQL、长事务、连接泄漏、数据库不可达，或并发量超出当前容量。
区分方法：长事务需检查事务持续时间和锁等待；连接泄漏需跟踪借出未归还的调用路径；数据库不可达需独立检查网络和认证。
不要仅根据获取连接超时就断言连接泄漏，也不要先盲目增大 maximumPoolSize。
验证：在隔离环境改变 SQL 延迟或事务范围，观察 pending 与响应时延变化。

```