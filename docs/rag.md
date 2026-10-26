# 2.0 历史故障知识检索

## 数据流

人工核验的 JSON 文档 → 脱敏 → 有行号的重叠切块 → 可选 Embedding → 原子替换索引。

Agent 自主调用 `search_knowledge` → 仓库/组件/版本过滤 → BM25 与余弦双路召回 → RRF 融合 → 知识片段 → 报告独立引用。当前源码继续走 ripgrep/AST。

默认 SQLite 保存文档与向量，进程内计算精确余弦；PostgreSQL 后端通过 pgvector `<=>` SQL 计算精确余弦。两个后端共用支持中文双字及英文标识符的 BM25。当前全库上限 5000 块，BM25 扫描候选语料；未配置倒排索引或 HNSW，不宣称支持大规模知识库。

## 知识格式

只读取用户明确指定的 JSON，不扫描仓库、测试或评测答案：

```json
[
  {
    "id": "pool-timeout",
    "title": "连接池等待超时排查",
    "source": "internal://runbooks/pool-timeout",
    "revision": "2026-10-23",
    "repository": "order-service",
    "component": "hikari",
    "versions": ["5.1.0"],
    "kind": "runbook",
    "content": "症状、候选原因、检查步骤、反例和验证方式。\n不要将假设写成已经验证的结论。"
  }
]
```

- `kind` 为 `runbook/postmortem/fix`。维护者在入库前核验来源与适用范围；系统不验证外部 URL，也不自动从模型报告学习。
- `repository` 默认 `global`，表示通用手册。诊断默认使用仓库目录名，可传 `--knowledge-repo order-service`。这是适用范围选择，不是多租户权限控制。
- `versions` 为空表示不限制版本；非空时，查询版本必须精确匹配。暂不推断 Maven 版本或解析语义版本范围。组件与版本可通过工具参数或 search 命令指定。
- index 原子替换指定 corpus 的完整快照，未包含的旧文档被移出。不同 corpus 不应复用相同文档 ID/内容；冲突回滚。拒绝空输入，避免误清空。
- 上限：500 份文档、5 MB 输入、每文档 100000 字符、单行 1500 字符。按完整行切块，每块约 1600 字符，相邻块一行重叠；长段落请换行。
- SHA256 覆盖脱敏后的规范化内容及元数据。引用包含文档 ID、来源、修订号、行范围、片段；结束前检查引用确由本任务返回且仍存在于当前索引。内容变更需重新 index，系统不监视原始 JSON 文件变化。
- 内容及 Embedding 端点/模型一致的块复用向量。端点或模型变化后重新 index；同名模型替换权重时也应更改模型标识并重建索引。

## 本地与语义检索

```powershell
.\.venv\Scripts\devtriage knowledge index --source knowledge/runbooks.json --corpus runbooks
.\.venv\Scripts\devtriage knowledge search "Hikari Connection is not available" --component hikari --mode keyword
.\.venv\Scripts\devtriage knowledge search "事务为什么没有回滚" --component spring-tx --version 6
```

在 `.env` 配置独立 Embedding 服务，接口接受 `POST <base>/embeddings` 和 OpenAI-compatible 请求/响应。base 通常含 `/v1`，例如 `http://localhost:8000/v1`，配置项见 `.env.example`。入库向该服务发送**脱敏后的知识标题与片段**，查询发送脱敏查询文本。对话模型按现有工具协议接收命中片段。

配置后重新 index；支持 `--mode hybrid`（默认）、`dense`、`keyword`。请求每批最多 32 条，20 秒超时，校验数量、顺序、维度、有限数值与非零向量。未配置、模型不兼容或检索时接口失败则明确标记 `mode=keyword` 和 warning。入库时接口失败保留旧索引。

RRF 使用 `sum(1/(60+rank))`，每路只融合前 30 个命中。余弦低于 `DEVTRIAGE_RAG_MIN_SIMILARITY`（默认 0.55）的结果被丢弃，阈值需针对实际模型调校。BM25 无匹配词时返回空列表，但少量关键词重叠仍可能误召回。排名分数不是根因置信度；没有相关知识时仍可依据源码诊断。

## PostgreSQL/pgvector

```powershell
.\.venv\Scripts\python -m pip install -e ".[rag-postgres]"
$env:DEVTRIAGE_KB_PASSWORD='replace-with-your-local-password'
docker compose -f knowledge/compose.yaml up -d --wait
```

然后在 `.env` 设置：

```dotenv
DEVTRIAGE_RAG_BACKEND=postgres
DEVTRIAGE_RAG_DSN=postgresql://devtriage:YOUR_PASSWORD@localhost:15432/devtriage
```

DSN 特殊字符需要 URL 编码，凭据与 Compose 一致。首次连接创建 `vector` 扩展和 `dt_knowledge` 表，需要数据库权限；生产环境应由迁移账号建表。SQLite 与 PostgreSQL 索引独立，切换后重新 index。Compose 仅绑定本机端口，down 保留数据卷。

可选 psycopg 驱动不在首版 `requirements.lock` 中，安装 optional extra 单独解析；SQLite 不新增锁定依赖。CI 增加独立 pgvector 集成测试，配置不代表远端 CI 已执行。

## 报告与边界

通过现有可信扩展接口注册 `search_knowledge`，没有任意 URL 抓取、SQL 或 Shell 工具。文档均为不可信数据，系统提示要求忽略其中的指令，但不宣称已抵御所有提示注入。

`knowledge_ids` 只能引用本任务收到的知识 ID，`knowledge` 由执行器重新填充，模型自填片段被覆盖。知识 ID 不能充当 `evidence_ids`；`supported` 仍要求当前日志与源码，`reproduced` 仍要求隔离实验。裁剪上下文保留知识 ID。设 `DEVTRIAGE_RAG_ENABLED=false` 可关闭工具。

## 评测

```powershell
.\.venv\Scripts\devtriage knowledge eval --dataset evals/retrieval.json
.\.venv\Scripts\python -m pytest -q
# 仅在专用数据库测试 pgvector
$env:DEVTRIAGE_TEST_RAG_DSN='postgresql://devtriage:YOUR_PASSWORD@localhost:15432/devtriage_test'
.\.venv\Scripts\python -m pytest tests/test_knowledge.py -q
```

比较 keyword/dense/hybrid，输出 Recall@5、MRR、无答案拒检比例与耗时，写入 `.devtriage/retrieval-latest.json`。expected 标签仅参与评分，不传给检索器。若模式回退，则 `fully_available=false`、`averages=null`，观测结果放 `fallback_averages`，不能据此宣称向量效果。

八条评测是开发冒烟集，五份手册是示例知识，不是保留测试集或生产复盘。按仓库或故障家族补充真实保留数据后才能评估诊断增益。确定性向量夹具只能验证计算与接线，不能证明真实模型语义效果。

`examples/rag-smoke` 提供合成日志与源码片段，非可部署应用。日志支持连接获取超时，单凭该输入无法区分慢 SQL、长事务或连接泄漏。
