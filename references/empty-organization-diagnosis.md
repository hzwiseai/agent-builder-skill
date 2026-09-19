# 空组织诊断

当 `design_get_organization_overview` 返回 `organization_state: empty` 时，当前
组织没有自有岗位，也没有 AI 成员；因此不存在可读取的运行记录、资源绑定或对话
证据。这是**诊断的终点**，不是“健康”结论，也不是让用户从空列表里选择目标的
信号。

## 先确认归属，再解释空白

调用 `design_get_organization_identity`，把其 `org_id`、`org_name`、`org_role`
和 `user_created_at` 与空概览一起报告。只根据这些返回值说明当前登录账号及其
组织；不要从默认组织名或创建时间猜测用户意图。

将可见的 `scope: system` 资产、话术包和岗位模板明确称作**平台库**，不要计入
组织自有内容，也不要逐项罗列它们来代替组织诊断。`attention: []` 只表示没有
现存对象可检查。若额外调用 `design_list_assets`，以每条返回记录的 `scope` 判断
归属，不要根据可见总数或分页元数据推断组织内容。

## 给出两个可选方向

1. **这就是目标组织**：说明它已具备开始条件。先让用户选择平台岗位模板和精确
   匹配的知识中心模板；仅在用户明确同意后，按“创建新岗位”流程物化。物化会发布
   首个组织岗位，不能作为诊断步骤自动执行。
2. **用户原本期待已有业务内容**：说明当前凭据对应的组织没有这些内容；请用户
   改用拥有该组织的账号后重新认证。不要把修改 `WISECOPILOT_ORG_ID` 当作通用
   修复手段：只有认证账号本来可切换多个组织时它才可能有效。

不要在空组织上调用 `design_get_conversation_evidence`、`design_list_runtime_runs`
或 `design_get_agent_resources`；它们无法增加证据。命令行排查时，如 MCP 尚未提供
身份工具，可使用只读的
`python scripts/design_api_client.py --operation organization-identity`，但不记录
或转发其登录凭据和访问令牌。
