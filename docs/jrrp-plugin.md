# 今日人品插件

[文档目录](README.md) · [插件开发](plugin-development.md) · [打包](packaging.md)

[qq_jrrp 示例目录](../example_plugins/qq_jrrp/botcraft.plugin.json) 将原 LazyBot/NoneBot 今日人品插件迁移为 BotCraft 插件，使用 QQ Markdown、命令键盘和被动消息回复。原 LazyBot 代码与语录数据不修改、不自动导入。

## 安装

将整个 `example_plugins/qq_jrrp` 目录复制到运行实例配置的插件目录，保留 `botcraft.plugin.json`、`qq_jrrp/`、`lang/`、`LICENSE` 和 `NOTICE`，不要只复制入口 Python 文件。根目录 `lang/` 由 BotCraft 自动注册，不需要插件手动加载。在仓库根目录安装到已初始化的测试实例：

```powershell
Copy-Item -Recurse .\example_plugins\qq_jrrp .\test\plugins\qq_jrrp
Set-Location .\test
python -m botcraft start
```

已运行的实例可在运维控制台执行 `/botcraft plugin refresh` 加载新插件。仅登记一个 `/jrrp` 帮助/面板项，不自行创建或接管远端面板。不要同时加载 ID 为 `qq_jrrp` 的目录与压缩副本。

## 查询与文字触发

以下收到的消息等效于纯 `/jrrp` 查询：

| 输入 | 支持的消息场景 |
| --- | --- |
| `/jrrp` | 群聊和 C2C；群 AT 消息会按框架规则去掉正文前导空格 |
| `@机器人 今日人品` | 群 AT 消息，平台去掉提及后匹配正文 |
| `今日人品` | 普通群消息、群 AT 和 C2C |
| `#今日人品` | 普通群消息、群 AT 和 C2C |

中文触发按整条真实正文匹配，忽略两端空白；不会匹配“看看今日人品”、附加参数、卡片、附件或引用内容中的词语。`/jrrp` 命令不会被消息监听重复响应。

**无 AT 的群消息必须先由 QQ 平台推送 `GROUP_MESSAGE_CREATE`。** 若账号或群未开启接收所有消息，本地插件不能补收平台没有推送的消息。C2C 无需机器人提及。

每个结果使用原消息 ID 发送被动回复。本次不实现引用展示：不需要 `msg_idx`，也不添加 `refer_msg` 或 `message_reference`。平台的被动回复时效、次数和 Markdown/键盘权限仍然适用。

## 评分、语录与按钮

- 每日评分沿用原算法：实际 `User.id` 和运行机器的本地日期共同决定结果；数字 ID 保留原数值种子，非数字 OpenID 使用 SHA-256。幸运指数为 0–100%，同一天同一身份固定。
- 不推断群聊与 C2C 的不同 ID 是同一个用户。更换运行机器时区可能改变日期切换时间。
- 初始语录池为空；已有语录池不变时，按旧算法最多选择三种每日候选语录。
- 仅投稿成功消息显示四个按钮，撤回按钮携带本条投稿 UUID；所有人都可点击，服务端检查执行者权限。其他场景仅显示一行「今日人品」「投稿」「帮助」。群聊按钮填入命令；C2C 今日人品/帮助按钮允许自动发送。投稿模板和撤回按钮不自动发送。
- 用户可使用 `/botcraft pref language set en_us` 切换输出语言；中文和英文内容来自根目录 `lang/`。正文通过带插件命名空间的 `rtr` 封装延迟求值，键盘标签/模板在发送前生成字符串。代码注释、异常与硬编码日志使用英文。

## 投稿与撤回

```text
/jrrp help
/jrrp post
/jrrp withdraw <id>
```

`/jrrp post` 展示投稿方法。点击投稿按钮填入模板，或直接发送以下多行消息：

```text
/jrrp post '''
在此填写语录，可以换行
'''
作者或出处
```

`post` 后必须保留一个空格，再写起始 `'''`；结束 `'''` 独占一行，出处写在下一行。正文内部空格与换行保留，普通引号和反斜杠不需要转义；正文不能包含独占一行的 `'''`。旧 `!文本` / `!出处` 模板不再支持。

命令树分别注册 `jrrp_handler`、`help_handler`、`post_handler` 和 `withdraw_handler`。`GreedyText` 仅收集 `post` 的投稿内容，由投稿解析函数检查标记与非空字段，不用于分派其他命令。

文本与出处均不能为空。`/jrrp withdraw <id>` 精确撤回指定 UUID 的投稿，仅投稿者本人或权限等级至少为 2 的用户可执行；拒绝操作不修改数据。投稿成功消息中的按钮自动携带 UUID，旧按钮指向已撤回投稿时仅提示不存在，不删除其他记录。相同官方 `User.id` 不再按 appid 或场景拆分，不推断不同 ID 属于同一个人。

语录存于运行实例的 `config/qq_jrrp/luck_sentence.json`，字段为 `id`（持久化 UUID）、`sender`、`sentence`、`from`。新投稿的 `sender` 仅保存通用官方 `User.id`。加载已有文件时，缺少 UUID 的记录自动补齐；符合 `appid:group|c2c:id` 格式的 sender 去掉 appid 与场景前缀，不区分旧 appid。其他旧身份值保留，不猜测归属。全部记录验证通过后才原子保存迁移结果，UUID 在重启后不变，重复投稿有不同 UUID。数据文件损坏时报告错误，不会清空覆盖；维护前备份。外部实例文件不自动导入。

## 分发许可

迁移插件保留来源与 **GPL-3.0-only** 许可，见插件目录中的 `LICENSE` 和 `NOTICE`。这不替 BotCraft 框架选择许可证。打包插件时需随包保留许可、来源说明与翻译资源：

```sh
botcraft pack -i example_plugins/qq_jrrp -o packed_plugins
```
