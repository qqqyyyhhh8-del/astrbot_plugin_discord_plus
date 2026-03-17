# Changelog

本文件记录 `astrbot_plugin_discord_plus` 的版本变更。

## [0.1.6] - 2026-03-17

### Added

- 新增 Discord 原生命令 `/discord_send_panel`，插件启动后会自动向已连接服务器同步注册。
- 新增仅管理员可见的中文 embed 管理面板，可切换服务器、服务器/分类/频道/线程粒度并批量调整发言权限。
- 面板支持“全选本页”“反选本页”“自动填充刷新”与发言权限覆盖总开关。

### Changed

- Discord 发言权限规则现在既可继续在 AstrBot 配置面板手动编辑，也可直接通过 Discord 原生面板写回同一份配置。

## [0.1.5] - 2026-03-17

### Added

- 新增 Discord 发言权限覆盖功能，可按服务器、分类、频道、线程四个粒度控制是否允许机器人回复。
- 新增管理员命令 `/discord_send_rules_refresh`，可自动填充当前 Discord 客户端可见的规则项。
- 新增管理员命令 `/discord_send_scope_here`，用于查看当前 Discord 作用域和发言判定。

### Changed

- 运行时在 `stop_event()` 后会停止继续分发后续 feature，确保发言权限覆盖能在等待 LLM 前截断回复。
- 发言权限规则使用 `template_list` 配置，并且默认 `allow=false`。

## [0.1.4] - 2026-03-17

### Changed

- 调整 Discord 艾特逻辑，引用回复本身不再默认艾特原消息作者。
- 只有消息链中实际存在 `At` 组件时，才会修复为 Discord 正确的成员提及。

### Fixed

- 为 Discord 原生引用回复显式关闭 `replied_user` / `mention_author`，避免误触发 ping。

## [0.1.3] - 2026-03-17

### Fixed

- 对 Discord typing 链路中的常见传输层错误做容错处理。
- 当连接被重置或类似网络异常发生时，停止 typing 循环而不是持续输出错误堆栈。

## [0.1.2] - 2026-03-17

### Changed

- 将回复引用实现从 AstrBot `Reply` 组件切换为 Discord 原生 `reply` / `reference` 发送。

### Fixed

- 让 Discord 中的引用回复真正生效。
- 当消息链无法安全转换为 Discord 文本时，回退到 AstrBot 默认发送逻辑，避免异常行为。

## [0.1.1] - 2026-03-17

### Changed

- 同步插件代码与元数据中的版本号到 `0.1.1`。

### Fixed

- 兼容插件目录半更新场景，避免因 `config.py` 或 `runtime.py` 版本不一致导致导入失败。

## [0.1.0] - 2026-03-17

### Added

- 初始版本发布。
- Discord typing indicator 支持。
- 面板配置项：`typing_enabled`、`mention_fix_enabled`、`reply_reference_enabled`。
- Discord `At` 修复能力和回复引用能力。

### Changed

- 重命名内部包，降低插件热更新时的缓存冲突风险。

### Fixed

- 修正 AstrBot 配置 schema 兼容性。
