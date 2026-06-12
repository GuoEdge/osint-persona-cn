# 贡献指南 / Contributing

感谢你对 OSINT Toolkit 的关注！

## 开发流程

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m "feat: add your feature"`
4. 推送分支：`git push origin feature/your-feature`
5. 发起 Pull Request

## 代码规范

- 使用 Python 3.10+ 类型注解
- 运行 `ruff check` 和 `ruff format` 保持代码风格一致
- 为新功能添加测试

## 模块开发指南

### 新增采集器 (Collector)

在 `src/osint_toolkit/collectors/` 下创建模块，实现数据采集逻辑，并在 `cli.py` 中注册命令。

### 新增分析器 (Analyzer)

在 `src/osint_toolkit/analyzers/` 下实现数据分析与关联逻辑。

### 新增导出器 (Exporter)

在 `src/osint_toolkit/exporters/` 下实现报告导出功能。
