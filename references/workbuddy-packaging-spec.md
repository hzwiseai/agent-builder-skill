# WorkBuddy Skill 打包规范

本规范固定 WorkBuddy 市场包的输入、转换和校验，避免上传时才发现
`SKILL.md` 元数据缺失。

## 必须结构

ZIP 中必须有 `SKILL.md`，并包含 YAML frontmatter。市场解析使用**顶层字段**，
不能只写在 `metadata` 下：

`name`、`description`、`display_name`、`display_name_en`、`description_zh`、
`description_en`、`version`、`author`。

`references/`、`scripts/`、`templates/` 为可选目录；WorkBuddy 包内路径最多两层。
不得包含 `.env`、`.session.json`、`.git`、缓存目录或上一次构建产物。

## 版本规则

`VERSION` 是唯一版本来源。打包器把它写入市场 frontmatter，并要求非空且一致。
版本采用三段式语义版本格式 `主版本.次版本.修订号`（例如 `0.1.1`），
不要使用两段式十进制（如 `0.11`）或日期字符串；每次发布必须递增。
上传 WorkBuddy 时，新版本必须严格大于平台已发布版本。
任何功能、提示词、参考文档、脚本或打包规则变更都必须升级版本；禁止用原版本号
覆盖已发布包。升级前先读取线上当前版本，按 SemVer 增加 patch/minor/major，发布后
把版本号和 ZIP SHA-256 记录到变更日志。

## 标准流程

```bash
conda run -n wiseai python scripts/package_skill.py --workbuddy \
  --out workspace/dist/wisecopilot-workbuddy
```

打包器会依次执行：排除本地配置 → 注入顶层市场元数据 → 校验必填字段与版本 →
完整性封存 → 检查目录层级 → 生成 ZIP。任一步失败都不应上传产物。

## 发布前检查清单

1. `SKILL.md` 能被 Skill 校验器读取。
2. ZIP 内 `SKILL.md` 的八个必填字段均为顶层且非空。
3. `version` 与 `VERSION` 一致，并高于线上版本。
4. ZIP 不含凭据、会话文件、缓存和嵌套旧 ZIP。
5. WorkBuddy 包中 `SKILL.md` 位于 ZIP 根，任意文件路径不超过两层。
6. 上传前保留打包命令输出和 ZIP 的 SHA-256，便于审计和复现。
