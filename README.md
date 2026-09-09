# Agent Builder Skill

用于 WorkTool V2 的 WiseCopilot 技能，通过 Design MCP 检查和设计岗位、任务技能、业务资产与 Agent 实例。

仓库名称为 `agent-builder-skill`，技能标识保留为 `wisecopilot`。本仓库只包含客户端技能与辅助脚本，需要连接可用的 WiseCopilot Design MCP 服务。

## 使用

1. 下载或克隆本仓库，将目录作为技能安装到支持 `SKILL.md` 的客户端。若客户端按技能名组织目录，请使用 `wisecopilot` 作为安装目录名。
2. 使用 Python 3.10 或更高版本，安装脚本依赖：

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   cp .env.example .env
   ```

3. 在本地 `.env` 填写服务地址、账号、密码，以及可选的组织 ID。示例地址需按实际部署修改；组织管理员需要启用 WiseCopilot 外部设计访问。
4. 按客户端的 MCP 配置方式注册 Streamable HTTP 服务。`mcp.json` 描述连接约定，不是所有客户端都能直接导入的配置文件。
5. 让客户端读取 [SKILL.md](SKILL.md)，通过 `design_authenticate` 建立会话，再执行组织内的设计任务。

系统资产只读；组织修改遵循技能定义的预览与确认流程。运行时支持的字段与工具以连接服务返回的契约为准。

## 目录

- `SKILL.md`：技能入口与操作流程。
- `references/`：V2 资产编写与 Design MCP 参考。
- `scripts/`：MCP 客户端、资产文件操作、完整性校验和打包脚本。
- `workspace/`：本地运行产物，除说明文件外不提交。
- `.env.example`：配置示例，不含登录凭据。

## 维护与打包

修改后更新完整性清单：

```bash
python scripts/_integrity.py --bless
python scripts/_integrity.py --verify
```

配置服务后，可检查文档中的工具名称：

```bash
python scripts/check_references.py
```

生成带完整性校验的发布包：

```bash
python scripts/package_skill.py
```

输出位于 `workspace/dist/`。Git 工作目录保持可编辑，发布包副本会封存为 `released`。不要提交 `.env`、`.session.json`、客户对话或运行产物。

更多说明见 [维护文档](references/maintaining.md)。
