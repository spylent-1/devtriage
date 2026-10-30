# 0.3.0 迁移验证

日期：2026-10-30（Asia/Shanghai）。本地 Python 自动测试 50 passed、4 skipped；独立实验场 JUnit 6 passed。Windows 干净环境按锁文件安装、pip check 和 wheel 构建通过。

真实模型冒烟覆盖六个场景：正常日志、源码不匹配和 RAG 证据不足均为 `insufficient`；三个实验故障均为 `reproduced`，对应异常断言与健康对照通过。[逐项任务和结果](evidence/release-20261030/summary.json)。这些是本地实验与合成输入，不能外推生产准确率。

本地全新实验镜像构建时 Ubuntu 软件源返回 502，因此本次实验复用了本机既有镜像；GitHub Actions 以全新 runner 构建实验场并执行集成验证。Windows、Linux、Docker/JUnit 和 PostgreSQL/pgvector 的具体结果以 [Actions](https://github.com/spylent-1/devtriage/actions) 对应提交为准。Embedding 服务与 Langfuse 云端仍未验收。

下面的 0.2.0 记录是历史结果，不代表 0.3.0 测试数据。

---

# 发布验收记录 · 0.2.0

日期：2026-10-26（Asia/Shanghai）。[历史验收记录](validation-history.md) 保留 2026-10-23 的原始结果，不混用两次测试数字。

## 本次发布前检查

- Windows / Python 3.12：**52 passed，0 skipped，35.28 秒**，包含三个 Docker 实验与一个真实 PostgreSQL/pgvector 集成测试。
- 新增三个源码搜索回归测试：保护目录与合法源码同时命中、嵌套模块、路径越界、文件消失/不可读取、搜索进程失败。
- 修复：搜索命中受保护目录时不再终止整个搜索；合法结果保留，直接读取保护路径仍拒绝。目录保护统一忽略大小写。
- Docker Engine 29.9.2；Spring Boot / MySQL / Redis 健康；pgvector 测试使用独立容器和专用数据库，宿主仅绑定 `127.0.0.1:15433`。
- pgvector 使用确定性向量夹具，验证真实 SQL 存取和余弦检索；不代表真实 Embedding 语义质量。

本次全量命令（先启动实验场与专用数据库并安装 `.[dev,rag-postgres]`）：

```powershell
$env:DEVTRIAGE_LAB_INTEGRATION='1'
$env:DEVTRIAGE_TEST_RAG_DSN='postgresql://devtriage:test-only@localhost:15433/devtriage_test'
.\.venv\Scripts\python -m pytest -q --basetemp tmp/pytest-release-all -p no:cacheprovider
```

`test-only` 只用于临时本地测试库。测试会替换其中的 `test` 语料，不能对业务数据库执行。

## 冷启动问题与修复

首次远端实验场检查发现 MySQL 初始化竞争：原 `mysqladmin ping -h localhost` 在临时 Socket 服务阶段就返回成功，应用在 TCP 3306 尚未就绪时启动并报连接拒绝。健康检查改为通过 TCP、使用应用账号连接 orders 库执行 `SELECT 1`。本机使用全新 `devtriage-release-cold` Compose 项目与数据卷冷启动，MySQL、Redis、应用均达到 healthy；远端使用全新 runner 再执行完整实验场检查。

## 安装与构建

从 Git 待发布文件导出干净目录，创建独立虚拟环境后，按 README 的 Windows 命令安装锁定依赖与 editable 包，执行 doctor、五份手册入库、中文检索和八条检索集评测，均成功。`pip check` 无冲突。`python -m build --wheel --no-isolation --outdir tmp/release-wheel-20261026` 成功，wheel 含 README 元数据与 MIT LICENSE。旧 dist 中同名文件覆盖有权限限制，因此本次使用新的构建输出目录。

## 本次真实模型冒烟

使用现有 DeepSeek 配置执行六个场景，全部满足预期；这不是独立准确率评测。

| 输入 | 结果 | 公开证据 |
| --- | --- | --- |
| 正常日志 | insufficient | [报告](evidence/release-20261026/normal-report.md) |
| 不匹配的源码 | insufficient | [报告](evidence/release-20261026/missing-source-report.md) |
| 连接池 RAG 合成案例 | insufficient，保留独立知识引用 | [报告](evidence/release-20261026/rag-report.md) |
| 实验场查询空值 | reproduced | [报告](evidence/release-20261026/case-1-report.md) / [JUnit](evidence/release-20261026/case-1-junit.xml) |
| 实验场唯一键冲突 | reproduced | [报告](evidence/release-20261026/case-2-report.md) / [JUnit](evidence/release-20261026/case-2-junit.xml) |
| 实验场缓存序列化 | reproduced | [报告](evidence/release-20261026/case-3-report.md) / [JUnit](evidence/release-20261026/case-3-junit.xml) |

[逐项结果与任务 ID](evidence/release-20261026/summary.json)。三个实验场输入来自本次 HTTP 500 请求与容器日志；每份 reproduced 报告均包含实际实验结果及健康对照。RAG 案例缺少运行时指标，历史知识未被当成已确定的根因。

## CI 与发布状态

[GitHub Actions](https://github.com/spylent-1/devtriage/actions/workflows/ci.yml) 对每个 push / pull request 执行四个检查：Windows Python、Linux Python、Docker 实验场、PostgreSQL/pgvector。Python 作业默认跳过集成用例；后两个作业分别实际执行对应集成用例。远端结果以具体提交对应的运行记录为准。

## 证据阅读约定

`docs/evidence` 中历史报告保留原始任务 ID、证据 ID、文件指纹、模型输出与执行结果。公开副本仅将实验产物的本机绝对路径改成项目相对路径；引用行中的空白和证据文本不改动。模型报告中的路径不是发布后的下载地址，实验 JUnit 文件以同目录链接为准。

历史案例来源于独立本地实验场；`examples/logs` 和 `examples/rag-smoke` 是合成输入。历史 12 条诊断基线与八条检索集是调试后的开发集，不能外推为生产准确率。

## 可选能力的未验收范围

- 未配置真实 Embedding 服务：不宣称 dense/hybrid 召回增益。
- 未配置 Langfuse Public/Secret Key：云端 Trace、Dataset、Experiment 尚未验收；SDK 契约和断线隔离由测试覆盖。
- 不提供自动修复、Web UI、通用生产环境实验执行或诊断任务自动恢复。
