# AI 可控介入

## 配置文件

- 持久导向: `%USERPROFILE%\.osint\ai_directives.yaml`
- Prompt 覆盖: `%USERPROFILE%\.osint\prompts\*.md`

## 命令

```bash
osint ai directives show
osint ai directives edit
osint ai prompts list
osint ai prompts edit summarize
osint search "话题" --ai-instruct "只关注实操"
osint search "话题" --no-ai-step persona_simulate
```

## 原则

硬约束 > 用户 prompt > 软偏好 > Persona 推断。AI 不静默删除采集结果。
