# DevTriage 9f9becb283ec4dafb4d0ecef6c245c99

状态：insufficient

checkout 调用在获取数据库连接时抛出 java.sql.SQLTransientConnectionException：HikariPool-1 - Connection is not available, request timed out after 30000ms，请求等待 30 秒后失败。

## 根因

日志与源码可确认失败点是 OrderService.checkout 第 12 行从 Hikari 连接池获取连接时等待 30 秒超时，说明请求时刻连接池无可用连接。但仓库仅含一个合成示例类，缺少 Hikari/数据源配置、事务与其它 DAO 代码，且无运行时池指标（active/idle/pending）、数据库活动会话、慢 SQL 与线程栈，因此无法判定是慢 SQL、长事务、连接泄漏、数据库不可达还是并发超出容量。checkout 自身使用 try-with-resources 获取并归还连接，未见明显泄漏路径，故根因类别保持 unknown。

位置：OrderService.java:demo.OrderService.checkout:12-15

## 修复建议

- 采集运行时证据：Hikari 池指标（active/idle/pending/total、等待队列长度）、connectionTimeout 与 maximumPoolSize 实际生效值。

- 抓取超时时刻的线程栈与数据库活动会话，判断是慢 SQL/锁等待、长事务还是连接未归还。

- 开启 leakDetectionThreshold 并跟踪借出未归还的调用路径，确认是否存在连接泄漏。

- 独立检查数据库可达性、网络与认证，排除数据库侧不可用导致的连接创建失败。

- 在补齐配置与运行时数据前，不要仅凭该超时盲目调大 maximumPoolSize。

## 证据缺口

- 仓库中不存在 Hikari/数据源配置文件，无法核对 maximumPoolSize、connectionTimeout、leakDetectionThreshold 等参数。

- 缺少运行时连接池指标（active/idle/pending）与数据库活动会话、慢 SQL、线程栈。

- 仓库仅含合成示例类 OrderService，缺少真实事务边界、其它 DAO 与调用方代码，无法评估泄漏或长事务路径。

- 日志无时间戳与关联 ID，无法与部署变更或流量峰值对齐。

- 未执行任何实验室验证（verify=none），无复现结果。

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

### 2f492edc1345d453 OrderService.java:12-12

SHA256: 836e8db6bfc4ef8f50866b761ad5d130e88b337ed3453ad33cec54853cf36217

```text

        try (Connection connection = pool.getConnection()) {

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