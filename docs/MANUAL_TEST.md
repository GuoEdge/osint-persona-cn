# Windows 本机验收清单

1. 设置 `DEEPSEEK_API_KEY` 用户环境变量
2. `pip install -e ".[dev]"`
3. `osint auth sync-cookies --browser edge`
4. `osint auth test --target all`
5. `osint search "测试话题" --trace`
6. `osint search "测试话题" --digest --no-ai`（无 API 时）
7. `osint save <知乎或B站URL> --with-comments`
8. `osint recall "测试"`
9. `osint ingest browser --since 30`
10. `osint persona build --review`
11. `osint run list` / `osint run show <run_id>`
