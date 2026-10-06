# 插件开发

[文档目录](README.md) · [部署与配置](configuration.md) · [插件打包](packaging.md)

插件从 `botcraft.api` 导入公开接口。使用 MCDR 的命令节点、插件元数据和生命周期，但消息来源是 QQ，消息内容是 `str`、`QText`、`QMarkdown` 或延迟翻译文本。不要通过框架私有字段访问内部服务。

`example_plugins/` 是面向开发者的示例：保留类型声明、模块来源/许可说明及必要的英文解释性注释，不为示例函数编写 API 式参数/返回值 docstring；库的公共 API 方法则提供完整方法说明。

库的 API docstring 使用英文 Sphinx/reStructuredText 字段语法：首段描述行为，`:param name:` 说明参数，`:return:` 说明返回结果，明确的异常条件使用 `:raises ExceptionType:`。类型以函数签名的声明为准，不重复维护 `:type:` 或 `:rtype:`。无输入参数时不写空参数区块，不返回结果的拒绝操作只记录异常条件；示例插件仍以解释性注释为主。

```python
from botcraft.message.qtext.text import escape_markdown as _escape_markdown

def escape_markdown(text: str) -> str:
    """Escape literal text for a QQ Markdown message.

    :param text: Literal text to escape.
    :return: Text with HTML and Markdown characters escaped.
    :raises TypeError: The input is not a string.
    """
    return _escape_markdown(text)
```

## 第一个命令插件

保存为实例的 `plugins/echo.py`，启动后在群聊或 C2C 发送 `/echo Hello world`：

```python
from botcraft.api.command import CommandContext, GreedyText, Literal, QQCommandSource
from botcraft.api.types import QQPluginServerInterface

PLUGIN_METADATA = {
    'id': 'echo',
    'version': '1.0.0',
    'name': 'Echo',
    'description': 'Reply with the supplied text',
    'dependencies': {'botcraft': '>=0.1.0'},
}


def echo(source: QQCommandSource, context: CommandContext):
    source.reply(context['text'])


def on_load(server: QQPluginServerInterface, prev_module):
    server.register_command(
        Literal('/echo').then(GreedyText('text').runs(echo)),
        scope=('group', 'c2c'),
    )
    server.register_help_message(
        '/echo',
        'Echo the supplied text',
        scope=('group', 'c2c'),
    )
```

也可直接复制[仓库 Echo 示例](../example_plugins/echo.py)到配置的插件目录。示例不会自动安装到运行实例；不要同时加载两个 ID 为 `echo` 的插件。`/botcraft plugin reload echo` 可重载已加载插件。

### 命令与帮助

- 命令根必须是 `Literal`；`GreedyText` 接收含空格的文本，也可使用 `Integer`、`QuotableText` 等公开节点。
- 根名称精确匹配注册值。框架不自动添加或删除 `/`，上例不能写成 `echo Hello world`。
- `GROUP_AT_MESSAGE_CREATE` 去掉 `message_data.content` 的前导 ASCII 空格。另有临时 dev 修正：`GROUP_MESSAGE_CREATE` 的正文开头（允许前导 ASCII 空格）若是 `MentionedUser.is_you is True` 且 ID 对应的 `<@id>`，移除一个标签及其后的 ASCII 空格。不处理 `<@!id>`、正文中间标签或重复后续标签，不猜测身份；条件不符保持原文。内部/尾部空格、引用元素、完整 mentions、raw_payload/data 与原始收件日志不变；C2C 不做此处理。
- `scope=('group',)` 将命令限制为群聊；`('c2c',)` 只允许私聊。默认两者皆可。命令和帮助分别登记 scope，保持一致。
- `register_help_message(prefix, message, permission=0, *, scope=..., only_admin=False)` 登记 `/botcraft help` 的帮助项及 QQ 帮助面板，`message` 支持英文字符串、语言字典或 `server.rtr(...)` 延迟翻译。面板使用实例配置语言，帮助查询使用当前来源语言；登记不替代命令权限检查。
- 用 `Literal('/admin').requires(lambda source: source.has_permission(2))` 检查实际执行权限；帮助的 `permission=2` 仅过滤帮助显示，`only_admin=True` 控制平台面板的管理员点击/操作资格，不保证其他用户看不到面板项。
- 帮助面板的名称为 1–14 字符，描述为 1–30 字符，不含控制字符。每个场景最多展示 20 项，超出项不影响命令注册；`server.get_panel_status('group')` 或 `('c2c')` 可查看状态及未展示的前缀。
- 运维控制台只执行内置 `/botcraft` 树，不是测试插件命令的 QQ 来源。`server.execute_command(command, source)` 必须使用本实例真实的 `QQCommandSource`。

## 消息来源、回复与结果

命令回调收到 `QQCommandSource`，常用字段为 `user`、`scene`、`conversation`、`msg_id`、`message_data` 和 `origin_received`。`source.get_server()` 返回 `QQServerInterface`，插件 `on_load` 收到绑定插件的 `QQPluginServerInterface`。

`source.reply(message)` 或 `server.reply(source, message)` 使用原始消息 ID 和原会话进行**被动回复**。不要自己构造消息来源、用编辑后的消息字段伪造路由，或把来源长期保存后继续发送；被动上下文有约 600 秒期限，也受原始平台时间和账号发送规则限制，过期会抛出 `PassiveReplyExpiredError`。

回复不是引用：若需要引用，显式传入 `refer_msg=received_message` 或同会话的 `QQMessageReceipt`；原消息必须有可用引用索引，跨会话或缺少索引会被拒绝。

### Future

发送、回复和撤回默认返回 `None`，表示已提交而不是平台确认。需要结果时传 `return_future=True`；返回 `concurrent.futures.Future`，成功发送结果为 `QQMessageReceipt`：

```python
import asyncio
from botcraft.api.exception import NetworkError


async def reply_result(source):
    future = source.reply('Accepted', return_future=True)
    try:
        receipt = await asyncio.wrap_future(future)
    except NetworkError as error:
        return {'status': error.category.value, 'message_id': None}
    return {'status': 'confirmed', 'message_id': receipt.receipt_data.id}
```

示例把已确认结果或失败类别交给调用者，不重复记录框架已经报告的网络失败。Future 回调不要执行耗时工作或假定仍在原命令上下文；需要时显式保留所需数据并使用 `server.schedule_task(...)`。异步协程可用 `await asyncio.wrap_future(future)` 等待，不要把普通 Future 直接 `await`，也不要在异步任务内调用阻塞的 `.result()`。

提交时的来源、类型、路由及 readiness 验证可能立即抛出异常；HTTP 和平台失败则由 Future 报告。`NetworkError` 提供 `category`、`http_code`、`err_code`、`code`、`trace_id` 等证据，不能靠中文或英文异常文字判断错误。`ResultUnknownError` 表示平台可能已经执行操作，不能盲目重发。

### 常用操作

| 接口 | 语义 |
| --- | --- |
| `server.say(target, message, return_future=True)` | 向 `User` 或 `Group` 主动发送，仍受 QQ 平台规则约束，不自动变成被动回复。 |
| `server.tell(user, message, return_future=True)` | 接收 `User`；群聊中附带对该用户的 AT。 |
| `server.broadcast(target, message, return_future=True)` | 向指定目标发送，不枚举所有群或用户。 |
| `server.reply_event(event, message, return_future=True)` | 仅接受真实 `GROUP_ADD_ROBOT` 或 `GROUP_MSG_RECEIVE` 事件，使用事件关联被动发送。 |
| `server.delete_message(received_or_receipt, return_future=True)` | 撤回收到的消息或发送回执所指消息，实际权限由平台决定。 |
| `server.delete_message_with_id(target, id, return_future=True)` | 使用明确 `User`/`Group` 路由和消息 ID 撤回。 |
| `server.respond_interaction(event, code)` | 接收真实 `QQInteraction`，响应码为整数 0–5，直接返回 Future；成功、结果未知或仍在进行的提交不能重复响应。确定失败后可由插件明确决定是否重试。 |

`User.id` 是权限与偏好的真实身份；`user_openid`、`group_openid`、`member_openid` 是路由/AT 用的不同字段，不可互换。使用收到的 `source.user`，或用平台提供的真实 OpenID 构造主动发送目标。例如 `Group(group_openid=actual_group_openid)`，不要用用户 ID 当作会话地址。

`message_data.author` 使用 `User`；`message_data.mentions` 使用 `MentionedUser(User)`，可从 `botcraft.api.types` 导入。其 `is_you: Optional[bool]` 表示该提及是否指向当前机器人，缺失/null 为 `None`，不通过昵称或 READY 身份猜测。提及列表保留机器人自身及其他用户；判断正文是否以机器人提及开头，还需匹配对应 `id` 的实际标签。错误字段类型沿用整事件通用回退规则。

临时前缀修正仅封装在 `botcraft/event/dev_group_message_prefix.py`，解析器调用后写回模型正文，命令与所有回调读取同一结果；不改变事件类型或额外派发。平台修复后删除此模块和解析器导入/调用，保留 `MentionedUser` API。该功能没有持久配置、机器人身份缓存或网络状态查询。

## 事件与生命周期

插件可以定义以下自动发现的回调；`server` 是绑定该插件的接口：

| 回调 | 时机与参数 |
| --- | --- |
| `on_load(server, prev_module)` | 加载/重载；`prev_module` 可用于迁移上次模块状态，首次加载为 `None`。登记命令、帮助和翻译。 |
| `on_unload(server)` | 卸载，包括重载时旧模块退出；关闭插件资源和后台工作。 |
| `on_botcraft_start(server)` | 本次实例启动并达到 READY；此时可提交 QQ 操作。 |
| `on_botcraft_stop(server)` | 曾达到 READY 的实例开始正常停止；不是任意加载失败的清理钩子。 |
| `on_qq_event(server, event)` | 通用 `QQEvent` 平台事件。 |
| `on_message(server, event)` | `QQMessageReceived` 群聊/C2C 消息。 |
| `on_group_message(server, event)` | 两种群消息投递：`GROUP_AT_MESSAGE_CREATE` 和 `GROUP_MESSAGE_CREATE`。 |
| `on_c2c_message(server, event)` | C2C 消息。 |
| `on_interaction(server, event)` | `QQInteraction` 交互事件。 |

也可在 `on_load` 中调用 `server.register_event_listener('c2c_message_create', callback)` 显式注册，事件 ID 不区分大小写；回调仍接收 `(server, event)`。同一处理不要同时用自动回调和显式登记，否则可能重复响应。

`botcraft.api.event` 导出 `Event`、`PluginEvents` 和原生 `PluginEvent`/`LiteralEvent`，以及 QQ 入站类型 `QQEvent`、`QQInteraction`、`QQMessageReceived`。登记平台事件通常直接使用官方事件名字符串；本地自定义事件使用 `LiteralEvent('my_plugin.event')`，不属于 `on_qq_event` 的平台推送范围。

`on_group_message` 登记到框架事件 `botcraft.group_message`，不合并两个官方事件 ID。消息安排顺序为命令处理、`on_qq_event`、`on_message`、群消息统一回调、官方类型精确监听；C2C 保持原专用回调。各入口共享对象，不保证异步完成顺序。解析失败不调用消息类回调，仍交付全局及官方精确监听。

旧默认方法 `on_group_at_message` 已移除，无兼容别名；只处理平台 AT 投递的插件应改用以下精确订阅。全量事件也可能包含机器人提及，官方事件类型不等同于正文是否包含 AT。

```python
from botcraft.api.decorator import qq_event_listener

@qq_event_listener('GROUP_AT_MESSAGE_CREATE')
def handle_at_delivery(server, event):
    server.logger.info('Received platform AT delivery')
```

也支持自动发现 `on_group_at_message_create_event` 或显式登记官方事件名。精确监听仍接收同一个类型化消息，不是另一个原始 JSON 通道。统一回调与精确监听同时登记会分别调用；不要重复执行相同副作用。

`QQEvent` 提供 `event_type`、`event_id`、`sequence`、`raw_payload`、`data`、`model_parse_failed` 和 `parse_error`。`data` 是可编辑 JSON 视图，与保留原接收事实的 `raw_payload` 分开；不要修改 `raw_payload` 来改变身份、路由或被动回复资格。消息的结构化内容在 `event.message_data`。群 AT 空格处理只影响该正文视图，不改 `data` 或原始响应日志。

消息事件可调用 `event.get_command_source()` 获取原始消息来源；缺少真实身份、消息 ID 或路由时会拒绝创建。若同时实现命令和消息回调，不要假定命令已经消费消息、消息回调不会再收到它。

`on_load` 不表示已连接 QQ，热加载也不会重新触发整次实例的启动事件。需发送时检查 `server.is_ready()`，并处理连接状态变化造成的提交失败。

## 权限与语言

权限主题必须是实际 `User` 或 `QQCommandSource`。`source.has_permission(level)`、`source.get_permission_level()` 和 `server.get_permission_level(subject)` 查询当前有效值；不要把首次查询结果作为永久授权。

- 超级管理员由 `permission.super_admins` 中的真实 `User.id` 确定。
- 优先级为超级管理员、当前会话显式权限、全局显式权限、模式默认权限。
- `native` 默认 0；`role` 和 `mixed` 的群成员默认 0、管理员 2、群主 4，C2C 默认 0；未识别角色按 0。显式授权仍优先。
- `server.set_permission_level(subject, level)` 和 `remove_permission(subject)` 默认只操作当前会话；`global_scope=True` 才改全局授权。C2C 会话授权需要已记录且验证过的真实私聊路由。

用户语言存储在偏好中，默认跟随实例 `language`。`source.get_preference()` 或 `server.get_preference(source)` 返回偏好副本；修改后调用 `server.set_preference(source, preference)` 才会保存。语言必须是框架已加载的语言。

```python
def set_english(server, source):
    preference = server.get_preference(source)
    preference.language = 'en_us'
    server.set_preference(source, preference)
```

### 翻译

目录和压缩插件可在根目录 `lang/` 放置 `en_us.yml`、`zh_cn.yml` 等 JSON/YAML 文件；BotCraft 自动发现并注册，无需手动读文件。翻译键以插件 ID 为命名空间。例如 `lang/en_us.yml`：

```yaml
greet:
  hello: 'Hello, {name}!'
  help: 'Send a greeting'
```

单文件插件或动态翻译仍可在 `on_load` 调用 `register_translation(language, mapping)`。优先通过轻量封装返回延迟文本，不在构造时固定用户语言：

```python
from typing import Any
from types import ModuleType
from botcraft.api.command import QQCommandSource
from botcraft.api.qtext import QQTranslationText
from botcraft.api.types import QQPluginServerInterface

PLUGIN_ID = 'greet'

def rtr(server: QQPluginServerInterface, key: str, *args: Any, **kwargs: Any) -> QQTranslationText:
    return server.rtr(f'{PLUGIN_ID}.{key}', *args, **kwargs)

def greet(server: QQPluginServerInterface, source: QQCommandSource, name: str) -> None:
    source.reply(rtr(server, 'hello', name=name))

def on_load(server: QQPluginServerInterface, prev_module: ModuleType | None) -> None:
    server.register_help_message('/greet', rtr(server, 'help'))
```

`server.rtr(key, ...)` 延迟到展示/发送边界求值，`source.reply` 按当前用户偏好选择语言。Markdown 模板使用 `server.rtr(key, markdown=True, ...)`；模板保留 Markdown，普通字符串/`QText` 参数按纯文本转义，嵌套延迟文本在同一语言下求值。

仅在必须立即获取字符串的地方使用 `server.tr`，例如键盘标签、按钮数据、异常文本或明确的同步查询。即时求值可指定 `language=source.get_preference().language`，或在同步代码中使用 `source.preferred_language_context()`；该上下文不能跨 `await`。不应把延迟对象提前 `str()` 或作为不接受延迟文本的构造器字符串参数。

`botcraft.api.qtext` 也导出 `tr`、`rtr`，调用需要运行中的接口。缺少键默认记录英文错误并显示键，`allow_failure=False` 抛出 `KeyError`。插件硬编码日志、异常和注释使用英文，中文用户反馈通过翻译键提供。

## Markdown 与键盘

下面是可独立运行的离线烟测示例，不需要机器人凭据：

```python
from botcraft.api.qtext import (
    QMarkdown, QText, QKeyboardActionCommand, QKeyboardButton,
    QKeyboardCustom, QKeyboardPermission, QKeyboardRenderData,
)

keyboard = QKeyboardCustom([[
    QKeyboardButton(
        id='echo_button',
        render_data=QKeyboardRenderData(label='Echo', style=1),
        action=QKeyboardActionCommand(
            data='/echo Hello',
            permission=QKeyboardPermission(),
            enter=True,
            reply=True,
        ),
    ),
]])
message = QMarkdown('**Echo**: ').append(QText('<hello>')).set_keyboard(keyboard)
payload = message.to_payload()
assert payload['msg_type'] == 2
assert payload['markdown']['content'] == '**Echo**: &lt;hello&gt;'
button = payload['keyboard']['content']['rows'][0]['buttons'][0]
assert button['action']['type'] == 2
assert button['action']['data'] == '/echo Hello'
print('Markdown and keyboard payload verified')
```

将 `message` 交给 `source.reply(message)` 即可提交到 QQ；离线 payload 成功不代表账号已经获得 Markdown/键盘发送权限。

- `QText` 编码普通文本，`QMarkdown` 构造器中的字符串按 Markdown 处理。
- `QMarkdown.append(str_or_QText)` 会转义普通内容；追加 `QMarkdown` 保留 Markdown。`append`、`set_keyboard` 修改自身，`+` 生成副本，`copy()` 复制消息。
- 每条组合消息只能有一个键盘；重复组合键盘会拒绝，不会静默丢弃。
- `QKeyboardTemplate(actual_template_id)` 使用平台模板；自定义键盘以按钮行列表构造。
- `QKeyboardActionJump`、`QKeyboardActionCallback`、`QKeyboardActionCommand` 分别表示跳转、回调、命令；按钮的 `QKeyboardPermission` 控制平台交互权限，不代替服务器端命令权限检查。
- 键盘支持链式 setter，类型、按钮 ID 重复及字段约束会在编码时验证；最终长度、数量与账号能力仍需遵守 QQ 平台规则。

## 后台任务与卸载

`server.schedule_task(callable_or_coroutine, block=False, timeout=None)` 接收无参 callable 或已经创建的协程对象，返回 Future。它不是卸载时自动管理所有后台工作的承诺。

插件需保存自己创建的任务、计时器、连接和其他资源，在 `on_unload` 中停止提交、发出取消/停止信号并关闭资源。正在运行的同步工作不能仅靠 `Future.cancel()` 停止，应自行合作退出。不要让旧模块任务在重载后继续回复或登记命令；停止中的实例会拒绝新注册、新任务和新 QQ 操作。

`server.get_data_folder()` 创建并返回实例 `config/<plugin_id>` 路径，用于可写插件数据。目录/压缩插件的只读资源使用 `server.open_bundled_file(relative_path)`，单文件插件不支持此接口。注册的命令、帮助、事件和翻译随插件生命周期清除，插件自己创建的外部资源不会因此自动关闭。

## 与 MCDR 插件的差异

- 无 Minecraft 子进程、RCON 或服务端信息。相关宿主操作会抛出 `UnsupportedOperationError`，不是假成功。
- 原生 `RText` 不是 QQ 公共消息格式，不能直接传给 QQ 发送接口。
- 不支持构造插件命令来源；公共 `execute_command` 只接受真实 QQ 消息来源。
- `QQServerInterface.si()` 在 BotCraft 未运行时抛出异常；可选访问使用 `si_opt()`。插件回调应优先使用传入的 `server`，不要依赖原生 MCDR 全局接口。
- 相同的 `.mcdr` 压缩格式不表示 Minecraft 插件可以直接在 QQ 上使用；需迁移输入事件、身份、消息和宿主操作。
