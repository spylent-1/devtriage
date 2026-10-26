# Contributing

欢迎提供可复现的问题、诊断工具改进和测试。提交 issue 时请附上系统版本、执行命令、预期与实际结果，以及最小化且已脱敏的日志或源码片段。不要上传真实凭据或未经授权的业务数据。

## 本地开发

按照 [README](README.md#quick-start) 安装 Python 3.12+、ripgrep 和开发依赖。

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m build --wheel
```

Windows 使用虚拟环境中的 Python；如旧临时目录存在权限问题，指定新的 `--basetemp tmp/pytest-<unique-name> -p no:cacheprovider`。

默认测试不调用付费模型；三个 Docker 案例和一个 PostgreSQL 案例按环境变量启用。数据库测试必须使用专用测试库，因为测试会替换 `test` 知识语料。完整集成命令见 [验证记录](docs/validation.md)。

## 修改约定

- 每次改动聚焦一个问题；修复行为缺陷时添加回归测试。
- 日志、源码和检索内容均视为不可信输入。工具执行限制不能由模型输出放宽。
- `knowledge_ids` 只表示历史参考；当前证据放在 `evidence_ids`，实验状态由执行器校验。
- 保持 CLI 和报告格式兼容；若改变接口，在 PR 中解释迁移方式。
- PR 说明问题、改动和实际执行的验证。未运行的集成检查或外部服务请明确列出。
- 不将开发集成绩写成生产准确率，不使用模拟结果声称云服务已验收。
