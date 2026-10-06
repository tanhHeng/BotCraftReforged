# BotCraft 文档

这些文档面向部署者与 QQ 插件开发者。BotCraft 独立运行，MCDR 2.14.4 作为 Python 代码依赖安装，不需要 MCDR 实例或 Minecraft 服务端。

## 从这里开始

1. [部署与配置](configuration.md)：初始化、凭据、日志、备份和运维命令。
2. [插件开发](plugin-development.md)：从命令插件开始，了解消息来源、事件、权限、翻译和键盘。
3. [元数据与打包](packaging.md)：单文件、目录、压缩插件和分发命令。
4. [Echo 示例](../example_plugins/echo.py)：可直接放入实例插件目录的单文件插件。
5. [今日人品插件](jrrp-plugin.md)：完整目录插件，含 `/jrrp`、中文触发、语录投稿和命令按钮。

[返回项目首页](../README.md)。

## 源码开发与本地验证

需要 Python 3.10 或以上。在源码根目录执行：

```sh
python -m pip install .
python -m pip install -r requirements.dev.txt
python -m botcraft.compatibility.probes
python -m unittest discover -s tests -v
python -m build
```

版本唯一来源为 `botcraft.constants.core_constant.VERSION`。`python -m build` 生成 `dist/` 中的源码发行包和 wheel；生产安装不依赖开发工具或 `tests/`。

能力探测在临时目录运行，不连接 QQ、不加载用户插件；成功退出码为 0。行为回归测试使用本地服务，不需要部署凭据。`tests/` 是当前仓库忽略的本地回归目录：仅在本地存在时运行上述 unittest 命令，发行包或缺少该目录的源码副本不能据此宣称完成回归验证。

### 文档示例烟测

- [插件开发中的 Echo 插件](plugin-development.md#第一个命令插件)可以保存为实例 `plugins/echo.py`，也可以直接使用仓库中的同名示例。不要同时加载两个相同 ID 的插件。
- [Markdown 与键盘示例](plugin-development.md#markdown-与键盘)只构造消息，不连接 QQ。将代码保存为 `message_smoke.py` 后运行 `python message_smoke.py`，会验证编码字段并打印英文完成提示；不需要机器人凭据。
- 打包完成后，将实际生成的压缩插件放入实例的插件目录，使用 `/botcraft plugin list` 查看加载结果。

这些命令与示例是验证方法，不是本文已执行的验收结果。实际 QQ 烟测需要真实凭据和账号能力：分别记录群聊/C2C 收件、文本/Markdown/键盘、引用/撤回、权限和帮助面板的结果，不以本地成功代替平台验收。

目前不提供媒体发送、C2C 流式消息和菜单备份/恢复能力；不要把这些接口视为已实现的插件契约。
