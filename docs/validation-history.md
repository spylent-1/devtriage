# 历史验收记录（0.1.0 / 0.2.0）

验收日期：2026-10-23（Asia/Shanghai）。源码与测试均在本机实际运行；GitHub Actions 配置已提供，尚未推送仓库或运行远端 CI。

## 环境与部署

- Python 3.12.10；独立 `.venv` 已安装，`pip check` 无依赖冲突，`requirements.lock` 已保存。
- 本机 Java 24/Maven 3.9.14 编译成功；业务镜像与实验容器实际使用 Java 21，Spring Boot 3.5.7。
- Docker Desktop 4.96.3 官方签名安装程序安装成功；WSL 3.0.3 安装成功，Docker Engine 29.9.2 已可访问。
- MySQL 8.4、Redis 7.4、Spring Boot 应用三个容器均健康；应用地址 `http://127.0.0.1:18080`。
- Compose 配置解析通过；三个 HTTP 故障路径实际返回 500，按请求时间窗口保存独立日志。

## 测试与诊断

最终结果：**27 passed in 34.25s**，含三个 Docker 集成案例，无跳过。

完整测试命令（含 Docker 集成）：

```powershell
$env:DEVTRIAGE_LAB_INTEGRATION='1'
.\.venv\Scripts\python -m pytest -q --basetemp tmp/pytest-final -p no:cacheprovider
```

覆盖工具校验、动态注册、路径边界、AST、真实 ripgrep、完整证据行与过期指纹、嵌套异常、上下文预算、模型失败、重复调用、轮次限制、中断状态、SQLite、凭据脱敏、遥测断线及云实验异步回调契约。云 SDK 契约测试使用模拟客户端，不代表云端上传成功。

三类真实 HTTP 日志经过 DeepSeek 自主检索及隔离实验，报告状态均为 `reproduced`，每个实验的异常断言、预期服务栈帧和健康对照均通过：

| 案例 | 任务 ID | 报告与 JUnit 证据 |
|---|---|---|
| 查询空值 | d20c62fcbcc04480b93381feef586929 | [报告](evidence/case-1-report.md)、[JSON](evidence/case-1-report.json)、[JUnit](evidence/case-1-junit.xml) |
| 唯一键冲突 | e9cd86ea82624e8dae88d6070ddca3bc | [报告](evidence/case-2-report.md)、[JSON](evidence/case-2-report.json)、[JUnit](evidence/case-2-junit.xml) |
| 缓存序列化 | 91b7d2a8e4754060babf7d40d97849ce | [报告](evidence/case-3-report.md)、[JSON](evidence/case-3-report.json)、[JUnit](evidence/case-3-junit.xml) |

## 评测与实际边界

[12 条真实模型基线结果](evidence/evaluation-latest.json)：在固定合成日志集上，根因标签、方法定位、引用有效性和应答/拒答判断均通过全部样例。基线执行为 `verify=none`，复现指标显示 `null`（未启用），独立三类容器验证见上表。每条结果保留耗时及输入/输出/总 Token 用量。该结果只说明这套小型、同源合成案例可用，不代表陌生仓库或生产环境准确率。

初轮结果曾出现模型标签同义词和位置格式不统一，收紧输出要求后重新运行同一集合；结果属于提示调试后的开发集结果，尚无独立保留测试集。执行中修复了旧事件序列化导致的评测读取错误，使用检查点继续完成剩余案例。

[真实 Judge 冒烟结果](evidence/judge-smoke.json)：对一份已复现报告完成解释清晰度、修复建议实用性评分。Judge 分数为模型主观辅助指标，不验证根因正确性。

**待完成项：Langfuse 云端验收。** 当前环境未配置 Langfuse Public/Secret Key，因此未上传 Trace、Dataset 或 Experiment；已实现 SDK 接入并通过异步回调契约与断线隔离测试。配置 `.env` 后运行 `devtriage eval --dataset baseline --verify lab --judge --langfuse` 完成云端验证。

已实现范围不包含自动修复补丁、RAG、向量数据库、Web UI、自动续跑。诊断建议由模型生成，引用真实性校验不等同于语义正确性证明。

## 2.0 RAG 增量验收（2026-10-23）

上文为 0.1.0 首版历史记录；0.2.0 已新增 RAG 与可选向量存储，详见 [使用文档](rag.md)。

- 完整本地测试：`45 passed, 4 skipped in 2.62s`。跳过三个原有 Docker 实验和一个 pgvector 数据库测试；本轮环境未发现 Docker 可执行文件，也未配置 PostgreSQL DSN。
- 新增测试覆盖中英文 BM25、仓库/组件/版本过滤、语义独立召回、RRF 融合、低相似度拒检、增量向量缓存、索引原子性、过期/伪造引用、错误模型回退、Embedding HTTP 响应契约、非法向量/端点、上下文保留引用，以及知识不能单独支撑 `supported` 状态。
- 真实 CLI 完成五份示例手册入库及八条检索开发集评测：[结果](evidence/rag-retrieval.json)。关键词模式 Recall@5、MRR、拒检比例均为 1.0，只适用于这套小型开发集。未配置真实 Embedding 服务，dense/hybrid 评分为 null，回退结果单独记录。
- 真实对话模型端到端诊断：任务 `9f9becb283ec4dafb4d0ecef6c245c99`，调用 `search_knowledge`，引用 `hikari-timeout`，保留三条当前证据；因缺失运行时连接池/数据库数据返回 `insufficient`，没有断言已复现或确定为连接泄漏。[报告](evidence/rag-smoke-report.md)、[JSON](evidence/rag-smoke-report.json)。输入是 `examples/rag-smoke` 合成片段，不是实际服务事故。
- 早期冒烟在被父目录忽略的 tmp 仓库中耗尽八轮预算，未形成有效报告；修正为显式示例目录，并加强缺少运行时信息时及时收敛的提示后完成上述验收。该过程不能用于宣称独立评测成绩。
- `python -m build --wheel --no-isolation` 成功产出 `devtriage-0.2.0-py3-none-any.whl`。
- PostgreSQL/pgvector SQL 路径及真实 Embedding 模型效果尚未现场验收；已提供专用数据库集成测试和 GitHub Actions job，远端 CI 本轮未运行。确定性向量夹具和模拟 HTTP 测试不代表真实语义效果。
