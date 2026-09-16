# 慧言AI员工训练Skill（WiseCopilot）

为 AI 团队、AI 销售和 AI 客服平台中的 **AI 员工**设计岗位职责、任务技能、话术与应答边界。

本 Skill 通过 **WiseCopilot Design MCP** 服务工作：先诊断组织里已有的角色、
Agent 与话术包，再把业务需求转成有证据支撑的资产方案，最后以可追溯的方式
落地。它是可移植的，适用于任何支持 MCP 的客户端——Codex、Claude、WorkBuddy。

## 安装前准备

- 一个可登录的 WiseCopilot 账号（用户名 / 密码）
- Design MCP 服务地址，默认 `https://crm.wiseaio.com/design`
- Python 3.10+（脚本运行环境）

如需使用随 Skill 附带的命令行 MCP 客户端，先安装其唯一依赖：

```bash
python3 -m pip install -r requirements.txt
```

## 配置

把 `.env.example` 复制为 `.env`，放在 `SKILL.md` 同级目录，填入账号：

```bash
cp .env.example .env
```

| 变量 | 说明 |
| --- | --- |
| `WISECOPILOT_MCP_URL` | Design MCP 服务地址 |
| `WISECOPILOT_API_BASE_URL` | 只读诊断接口地址（`design_api_client.py` 使用） |
| `WISECOPILOT_USERNAME` / `WISECOPILOT_PASSWORD` | 登录凭据 |
| `WISECOPILOT_ORG_ID` | 可选。填写后会话锁定在该组织 |

`.env` 已被 `.gitignore` 忽略，**不要提交，也不要放进任何分发包**。打包脚本会在
构建后复查，一旦发现凭据文件会直接丢弃整个包。

## 在各客户端注册 MCP

连接契约统一在 `mcp.json`：`streamable-http` 传输，认证走 `design_authenticate`
工具握手（不是 HTTP Header）。各客户端的注册方式不同：

**Claude / Codex** —— 在客户端的 MCP 配置中新增一个 `streamable-http` 服务，
URL 取 `WISECOPILOT_MCP_URL` 的值。连接后由 Skill 调用 `design_authenticate`
完成登录，无需在客户端里配置密码。

**WorkBuddy** —— 上传 `--workbuddy` 模式打出的 ZIP（见下），平台会自动解析
`SKILL.md` 的 frontmatter 并生成技能。MCP 服务在平台侧配置。

WorkBuddy 的字段与目录约束见
[WorkBuddy Skill 打包规范](references/workbuddy-packaging-spec.md)。打包器会在封存
前自动补齐并校验顶层展示元数据；校验失败不会生成可发布包。

资产读取、修改和并发冲突处理见
[资产修改一致性规范](references/asset-concurrency-spec.md)。

平台注册、配置、使用和故障问题的处理边界见
[平台帮助问题工作流](references/platform-helpdesk-workflow.md)。
平台注册/登录地址为 <https://crm.wiseai.chat>，帮助文档为
<https://crm.wiseaio.com/help/manual>。
每次保存成功后，工具会回读线上版本并自动刷新本地基线 hash。

## 打包分发

```bash
# 标准版（顶层带 wisecopilot/ 目录，适用于 Claude、Codex）
python3 scripts/package_skill.py

# WorkBuddy 版（SKILL.md 位于 ZIP 根，路径最多两层）
python3 scripts/package_skill.py --workbuddy --out workspace/dist/wisecopilot-workbuddy
```

打包会把技能从 `design` 阶段封存为 `released`，并校验：

- `.env` 与 `.session.json` 未被打入（发现即丢弃整个包）
- `VERSION` 与 `SKILL.md` 的 `metadata.version` 一致（不一致则构建失败）
- WorkBuddy 模式下路径不超过两层（超限则丢弃）
- WorkBuddy frontmatter 的必填字段均存在且非空，并与 `VERSION` 一致

## 版本

版本的唯一来源是 **`VERSION`** 文件，`SKILL.md` frontmatter 里的 `metadata.version`
必须与它一致，否则构建失败。

发布新版本时两处一起改：

```bash
echo "0.0.3" > VERSION
# 同步修改 SKILL.md 的 metadata.version: "0.0.3"
python3 scripts/package_skill.py --workbuddy --out workspace/dist/wisecopilot-workbuddy
```

> WorkBuddy 要求每次上传的版本号**严格大于**平台上的当前版本，重复版本会被拒绝。

## 故障排查

| 现象 | 处理 |
| --- | --- |
| 构建报「版本校验失败」 | `VERSION` 与 `SKILL.md` 的 `metadata.version` 不一致，同步后重试 |
| 构建报「WorkBuddy 目录层级超限」 | 新增了三层路径的文件；WorkBuddy 只接受两层，需调整目录结构 |
| 构建报「packaged tree contained local configuration」 | `.env` 或 `.session.json` 混入了打包范围，检查 `staged_paths()` 的排除规则 |
| 完整性校验失败 | 分发包被改动过；重新打包，不要手工编辑已封存的文件 |
| 认证失败 | 核对 `.env` 中的用户名密码，以及 `WISECOPILOT_MCP_URL` 是否可达 |
| 工具不存在 | 服务端版本与文档不符，运行 `python3 scripts/check_references.py` 定位 |

## 目录说明

| 路径 | 用途 |
| --- | --- |
| `SKILL.md` | 技能定义与工作流程 |
| `references/` | 资产创作规范、MCP 契约、平台模板与行业示例 |
| `scripts/` | MCP 客户端、只读诊断、资产文件编辑、打包与完整性工具 |
| `requirements.txt` | 随附命令行 MCP 客户端所需的 Python 依赖 |
| `workspace/` | 单次运行的产物目录，不随包分发 |
