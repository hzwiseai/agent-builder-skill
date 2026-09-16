# 资产修改一致性规范

## 目标

Skill 对组织资产采用“乐观并发锁”：本地修改只能基于明确读取到的线上草稿版本提交，不能用整份文档无条件覆盖线上最新内容。

## 标准闭环

1. `design_get_asset` 读取当前组织草稿，保存 `asset_kind`、`asset_key`、`draft_key` 和 `content_hash`。
   这个 hash 是本地工作副本的唯一基线；同步时同时记录拉取/同步时间。
2. 只在本地副本上修改 `document`，不得删除 `asset` 信封或手工填写身份/hash。
3. `design_prepare_draft_save` 携带读取时的 `base_content_hash`；不一致返回 `design_draft_base_content_hash_stale`，必须重新读取并把修改重放到最新版本。
4. 展示 prepare 返回的 bounded diff，取得用户确认后再 commit。
5. commit 前服务端再次比较 prepare 基线；期间有并发修改则返回 `design_draft_confirmation_stale`，绝不写入。
6. 多资产变更使用 `design_prepare_draft_bundle_save`，按整包基线原子提交；任一资产变化则整个 bundle 拒绝。
7. 草稿保存后重新读取并检查，再单独走发布确认；草稿不会自动改变运行中的 Agent。
8. 提交成功后立即回读资产并把返回的最新 `content_hash` 写回本地工作副本，记录
   `previous_baseline_content_hash` → 新基线的链路。下一次修改只能从这个新基线开始。

## 禁止事项

- 禁止从旧导出文件直接上传。
- 禁止缺少 `content_hash` 时 push；工具必须要求重新 pull。
- 禁止把 published release hash 当作当前 org draft hash。
- 禁止绕过 prepare/commit 直接调用底层 PUT。
- 发生 stale 后不能自动覆盖或静默合并；必须重新读取、审阅冲突并重做。
- 禁止复用已成功提交但未刷新基线的旧工作文件继续修改。

线上先改、WorkBuddy 后改时，WorkBuddy 提交会被 stale 检查拒绝，不会覆盖线上改动。只有重新拉取最新草稿、重放本次变更并重新审阅 diff 后，修改才会写入。
