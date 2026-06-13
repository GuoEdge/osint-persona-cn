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

## 匹配方式

- 搜全名或任意别名均可命中整组关联词
- 搜简称（如「祥子」）也可命中全名词条（包含匹配）

## 规则兜底（可选）

默认仅在联网/词表仍不足 2 个关联词时，对 3–6 字中文名补「简称 / 小X」。  
若需要旧的「酱 / 碳 / 女士」机械后缀，在 config 设 `search.rule_nickname_suffixes: true`。
