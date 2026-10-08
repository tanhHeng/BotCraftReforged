# 部署与配置

[文档目录](README.md) · [插件开发](plugin-development.md)

## 安装与初始化

尚未发布到 PyPI。从源码根目录运行 `python -m pip install .`；`botcraft --version`、`python -m botcraft --version` 或 `botcraft version` 可以查询版本而不启动机器人。

运行实例与源码分开存放。在你选定的位置创建空目录：

```sh
mkdir botcraft-run
cd botcraft-run
botcraft init
```

`init` 创建缺少的 `config.yml`、`permissions.yml`、配置中的插件目录、`config/botcraft` 和 `logs`。已有文件不会覆盖；目录使用当前工作目录作为相对路径基准。填写本实例 `config.yml` 中的真实 `appid`、`secret` 后启动：

```sh
botcraft start
```

`python -m botcraft` 或不带参数的 `botcraft` 等价于普通启动。缺少配置或权限文件时，普通启动拒绝，不自动生成。显式选择 `start --auto-init` 才先补缺；空凭据仍必须填写后才能连接。

自定义文件路径时，在初始化和启动阶段使用一致参数：

```sh
botcraft init --config settings/config.yml --permission settings/permissions.yml
botcraft start --config settings/config.yml --permission settings/permissions.yml
```

首次启动会进行本地兼容性检查。`botcraft start --check-capabilities` 可强制重新检查；检查失败会拒绝启动。此检查不连接 QQ，也不是平台验收。正式启动会加载插件、重建群聊/C2C 帮助面板并等待网关 READY；账号权限和平台接口仍需实际验证。

## 常用配置

| 字段 | 默认值与含义 |
| --- | --- |
| `appid` / `secret` | 空；QQ 开放平台凭据。修改需要新进程启动。 |
| `language` | `zh_cn`；默认语言，可用 `en_us`。用户可以单独设置语言。 |
| `plugin_directories` | `[plugins]`；插件搜索目录，相对路径基于实例工作目录。 |
| `log_received_messages` | `true`；记录群聊/C2C 收件正文、会话与用户 ID 前六位，可 reload。 |
| `gateway.intents` | `[GROUP_AND_C2C_EVENT, INTERACTION]`；可增加 `MESSAGE_AUDIT`。 |
| `http.timeout` | `10.0` 秒；必须是有限正数。 |
| `permission.mode` | `mixed`；也支持 `native`、`role`，见[权限说明](plugin-development.md#权限与语言)。 |
| `permission.super_admins` | `[]`；真实 `User.id` 列表，不使用昵称或推测的跨场景身份。 |
| `advanced_console` | `true`；MCDR 风格高级输入、Tab 补全、多列候选菜单和参数提示，修改需要重启。 |
| `disable_console_thread` | `false`；是否关闭控制台线程，修改需要重启。 |
| `disable_console_color` | `false`；关闭控制台颜色。 |
| `debug.raw_response` | `false`；脱敏原始网关 JSON 和 HTTP 响应日志，可 reload，独立于 `debug.all`。 |

旧配置缺少选项时会按默认值补缺，首次加载可写回文件；不是把已有有效配置替换为默认值。对于凭据或控制台启动选项，reload 不能代替重启。

### 控制台输入与补全

开启 `advanced_console` 后，输入 `/botcraft` 可按 Tab 选择子命令，继续输入时显示多列候选与参数提示；语言设置补全当前可用语言，插件 reload/unload 参数补全已加载插件 ID。多行粘贴按行提交，日志输出不会覆盖正在编辑的命令。

控制台补全范围与执行范围一致：只提供内置 `/botcraft` 运维树，不把 `/echo`、`/jrrp` 等需要真实 QQ 来源的插件命令开放给控制台。插件加载/卸载和语言变更后，下一次补全读取当前状态。

设置 `advanced_console: false` 使用基本标准输入，不提供高级菜单。高级输入初始化失败时会记录英文错误并回退基本输入。`/botcraft exit`、EOF 或 Ctrl-C 请求停止；退出会唤醒高级输入并恢复控制台日志输出。

### 覆盖与重排

```sh
botcraft gen-default --config config.yml --permission permissions.yml
botcraft reformat-config -i config.yml -o formatted/config.yml
```

- `gen-default` **明确覆盖**两个目标文件，已有凭据和权限会丢失。执行前备份。
- `reformat-config` 校验后按默认模板重排，保留已知配置值；未知字段忽略并给出英文 warning。验证失败不写输出。
- `reformat-config` 不指定 `-o` 会覆盖输入文件。先输出到新文件核对，再决定替换；不要用它保存未知的自定义字段。
- 两者都不加载插件或连接网关；`init` 的补缺语义与 `gen-default` 的覆盖语义不同。

## 收件与诊断日志

日志输出到控制台和 `logs/botcraft.log`。硬编码的运行提示、异常说明与诊断日志统一使用英文；翻译键产生的帮助、命令反馈等仍可随语言配置输出中文。消息正文属于收到的数据，不会因日志语言改变而翻译。

`log_received_messages: true` 的消息部分示例：

```text
[Group:ABCDEF] [User:896C5A] Hello world
[C2C:UVWXYZ] [User:896C5A] Hello|Markdown text|[attachments] {"url":"https://example.org/file"}
```

只拼接实际存在的正文；附件、ARK、嵌套消息元素以带字段名的 JSON 展示。记录发生在命令与插件回调之前；群 AT 消息仅去掉前导 ASCII 空格，其他消息保留原正文。正常收件日志不显示消息 ID；群会话取原始 `group_openid`、C2C 会话取原始 `author.user_openid`，用户身份取原始 `author.id`，各仅显示前六位，不加省略号。缺少字段时显示 `-`，不会以路由 OpenID 冒充用户身份。换行和控制字符转义为单行，凭据仍脱敏。

设置 `log_received_messages: false`，然后在运维控制台执行 `/botcraft reload config`，可以关闭正常收件记录，不影响消息处理、异常报告或网关阶段日志。网关日志记录连接地址已取得、连接完成、READY、停止及必要的重连/失败；不逐条打印心跳、Token、Secret、完整网关地址或会话 ID。

排障时可显式开启 `debug.raw_response: true`。英文标记示例：

```text
Raw response [Gateway] {"op":11}
Raw response [HTTP] [send message] [http_code:200] {"id":"message-id"}
```

- 网关在解析前记录入站 JSON，包括 Hello、READY、消息和 ACK；HTTP 在业务校验前记录响应体、状态码和操作名，不记录出站请求或鉴权请求体。
- JSON 紧凑显示为单行，保留消息正文前后空格；非 JSON 响应显示转义文本，不承诺逐字节复刻。
- Token、Secret、鉴权字段、`session_id` 和网关地址脱敏，不修改业务数据。
- **原始日志仍包含完整消息 ID、用户 ID、群 ID 和聊天内容**，不使用正常收件的身份缩写。`debug.all` 不会自动启用此选项。

正常正文与富消息也可能含个人信息。排障结束后关闭原始日志；分享日志前审查隐私，不把自动脱敏视为可公开的保证。

## 运维命令与备份

群聊、C2C 和运维控制台统一使用 `/botcraft` 根；不能省略 `/`。发行包 CLI 则使用无斜杠的 `botcraft start` 等命令。

```text
/botcraft
/botcraft help
/botcraft pref
/botcraft pref language set en_us
/botcraft permission list
/botcraft plugin list
/botcraft plugin reload echo
/botcraft reload config
/botcraft reload permission
/botcraft reload preference
/botcraft exit
```

`/botcraft` 输出 BotCraft 版本及已登记帮助项的输入框标签；`/botcraft help` 输出 BotCraft 自身的 `help`、`perm/permission`、`plugin`、`pref/preference`、`reload` 和 `exit` 指令帮助。两者均按当前来源语言输出；内置面板仅登记 `/botcraft`。权限管理、插件操作、reload 和退出仅允许超级管理员或运维控制台；设置较高的普通权限等级不自动授予超级管理员身份。

`/botcraft plugin list` 沿用 MCDR 的纯文本分组：已加载项显示名称和 `id@version`，随后列出已禁用、未加载插件文件名及数量。不会打印完整 `Metadata(...)` 调试表示，也不输出 Minecraft 点击/悬浮样式。QQ 来源只发送一条按用户偏好语言生成的被动回复；控制台使用其偏好语言。

权限命令可在当前消息场景操作用户；控制台需明确指定 `--group`、`--c2c` 或 `-g/--global` 作用域。C2C 操作要求框架已经记录该用户的真实私聊路由。不要猜测或拼接 OpenID 来建立身份。

维护前备份 `config.yml`、`permissions.yml`、`config/` 与插件文件；`config/` 包含插件数据及用户语言等实例状态。特别是 reload preference 对损坏 JSON 沿用恢复语义，可能清空并重写偏好文件，应先备份。使用 `/botcraft exit` 正常停止；插件自身的后台任务应按[卸载责任](plugin-development.md#后台任务与卸载)收尾。
