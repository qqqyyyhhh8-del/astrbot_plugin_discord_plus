# astrbot_plugin_discord_plus

AstrBot 的 Discord 增强插件。

这个仓库当前先补上 AstrBot 原生 Discord 适配里缺失的一项体验：当 AstrBot 正在等待大模型返回结果时，让 Discord 客户端显示机器人“正在输入”。

English version: [README.en.md](./README.en.md)

## 简介

这个插件不是按“单功能脚本”来组织的，而是按“Discord 功能模块集合”来设计的。

当前已经实现：

- 在 `on_waiting_llm_request` 阶段显示 Discord typing indicator
- 在 `on_llm_response` 返回后自动停止 typing 状态
- 把默认 At 组件转换成 Discord 可识别的提及格式
- 回复 Discord 用户时自动引用原消息
- 按 Discord 服务器 / 分类 / 频道 / 线程覆盖是否允许机器人发言
- 提供管理员命令自动填充 Discord 发言权限规则
- 预留模块化结构，方便继续添加新的 Discord 专属功能

## 目录结构

```text
.
|-- main.py
|-- metadata.yaml
|-- requirements.txt
`-- astrbot_plugin_discord_plus_core/
    |-- runtime.py
    |-- discord_bridge.py
    |-- feature_base.py
    `-- features/
        `-- discord_typing.py
```

## 工作方式

`main.py`

负责注册 AstrBot 插件，并把 AstrBot 生命周期事件转发给内部运行时。

`astrbot_plugin_discord_plus_core/runtime.py`

负责统一分发事件到各个功能模块，避免以后所有逻辑都堆在入口文件里。

`astrbot_plugin_discord_plus_core/features/discord_typing.py`

负责实现“正在输入”功能：AstrBot 进入 `on_waiting_llm_request` 时启动后台 typing 循环，在 `on_llm_response` 后结束。

`astrbot_plugin_discord_plus_core/features/discord_mention_fix.py`

负责把 AstrBot 默认的 `At` 组件转换成 Discord 可识别的 `<@user_id>` 提及格式。

`astrbot_plugin_discord_plus_core/features/discord_reply_reference.py`

负责在 Discord 回复中改用原生 `reply/reference` 发送引用消息。

`astrbot_plugin_discord_plus_core/features/discord_send_permission.py`

负责按 Discord 服务器 / 分类 / 频道 / 线程规则覆盖是否允许机器人发言，并提供规则自动填充能力。

`astrbot_plugin_discord_plus_core/discord_bridge.py`

负责从 AstrBot 事件对象里尽量稳妥地找到 Discord channel 对象，并调用 Discord 的 typing API。这里用了较宽松的探测方式，目的是减少对 AstrBot 内部实现细节的硬编码依赖。

## 安装方式

1. 把这个插件目录放到 AstrBot 的 `data/plugins/` 下。
2. 确保插件目录名能被 AstrBot 正确识别，推荐直接使用 `astrbot_plugin_discord_plus`。
3. 在 AstrBot 管理面板中重载插件。
4. 到 Discord 中发送一条会触发 LLM 回复的消息，观察机器人是否会显示“正在输入”。

## 配置

插件现在带有一个可在 AstrBot 管理界面修改的配置项：

- `typing_enabled`
- `mention_fix_enabled`
- `reply_reference_enabled`
- `send_permission_override_enabled`
- `send_permission_rules`

关闭对应开关后，插件会保留加载状态，但会停止对应的 Discord 增强行为。

`send_permission_rules` 使用 `template_list` 维护四种粒度的规则：

- `guild`
- `category`
- `channel`
- `thread`

规则优先级为：`thread > channel > category > guild`，同级规则后面的覆盖前面的。启用发言权限覆盖后，未命中的 Discord 范围默认禁止发言。

## 管理命令

- `/discord_send_rules_refresh`
  从当前 Discord 机器人连接中扫描服务器、分类、频道、线程，自动填充 `send_permission_rules`，新规则默认 `allow=false`。
- `/discord_send_scope_here`
  显示当前 Discord 事件所在的服务器 / 分类 / 频道 / 线程 ID，以及当前是否允许发言。

## 后续扩展

如果后面要继续加 Discord 专属功能，建议按下面的方式扩展：

1. 在 `astrbot_plugin_discord_plus_core/features/` 下新增一个功能模块。
2. 基于 `FeatureBase` 实现新的 feature 类。
3. 在 `main.py` 的 `DiscordPlusPlugin` 中注册这个 feature。

这样可以把插件保持成“入口简单、功能独立”的结构，后面继续迭代时不会很快失控。

## 注意事项

- 这个插件默认假设 AstrBot 的 Discord 适配器会把 Discord 原始对象挂到事件上下文里。
- 由于不同 AstrBot 版本或适配器实现可能有差异，当前 typing 逻辑做了偏保守的兼容处理。
- 发言权限覆盖目前拦截的是会触发 LLM 回复的消息流程，用于覆盖“机器人是否在该 Discord 范围内回复”。
- 当前环境里我只做了本地语法级校验，没有在完整 AstrBot 运行时里做实机联调。
