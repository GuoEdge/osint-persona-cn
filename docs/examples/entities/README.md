# 实体关联词表

将 YAML 文件放入 `~/.osint/entities/`（例如 `bangdream.yaml`），搜罗时会自动合并关联词并行检索。

## 格式

```yaml
entities:
  丰川祥子:
    aliases:
      - 祥子
      - 小祥
    slurs:
      - 祥处   # 仅当 config.yaml 中 search.include_slurs: true 时启用
```

也可使用列表格式：

```yaml
entities:
  - canonical: 角色全名
    aliases: [昵称1, 昵称2]
    slurs: [黑称1]
```

仓库内示例见同目录 `bangdream.yaml`，可复制后按需修改。

## 自动沉淀

开启 `search.persist_discovered_aliases: true`（默认）后，联网发现的关联词会合并写入：

`~/.osint/entities/discovered.yaml`

下次搜罗同一查询时会自动加载，无需手动维护。
