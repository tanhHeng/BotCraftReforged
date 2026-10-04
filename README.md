# BotCraftReforged

**中文** | [English](README_en.md)

> 一个基于 [MCDReforged](https://github.com/MCDReforged/MCDReforged) 的、适配官方 QQ 机器人的开发框架。

BotCraftReforged 继承了 MCDR 的插件开发、指令管理、权限管理等方便的功能。你可以像开发 MCDR 插件一样开发 BotCraft 插件，同时使用面向 QQ 的消息与事件接口。

“Reforged” 既指 BotCraft 是 MCDR 的“重铸”，也是感谢与赞美 MCDR 的优秀设计。发行包名、Python import 命名空间和命令行入口均为 `botcraft`。

## 特点

- 独立运行，使用官方 QQ 机器人网关与 HTTP API，支持群聊和 C2C。
- 复用 MCDR 的插件生命周期、命令树、权限与翻译能力。
- 提供被动回复、文本、Markdown、键盘及帮助面板等 QQ 接口。
- 支持单文件、目录和压缩插件，便于开发与分发。

需要 **Python 3.10 或以上**。MCDR 2.14.4 是代码依赖，不是宿主；无需 Minecraft 服务端。

## 使用

目前尚未发布到 PyPI。在源码根目录安装：

```sh
python -m pip install .
botcraft --version
```

随后在独立的空目录初始化运行实例：

```sh
mkdir botcraft-run
cd botcraft-run
botcraft init
```

在生成的 `config.yml` 中填写 QQ 开放平台的 `appid` 和 `secret`，然后启动：

```sh
botcraft start
```

也可使用 `python -m botcraft`；无参数等价于 `start`。初始化只补缺，不覆盖已有文件。详细配置及运维命令见[部署与配置](docs/configuration.md)。

## 插件

将插件放入实例的 `plugins` 目录。先从 [Echo 示例](example_plugins/echo.py)开始：群聊或 C2C 输入 `/echo Hello world`，即可通过原消息来源被动回复文本。

[插件开发指南](docs/plugin-development.md)介绍命令、事件、权限、翻译和 QQ 消息；[打包指南](docs/packaging.md)介绍插件格式与分发。

## 文档

- [文档目录与开发验证](docs/README.md)
- [部署、配置、日志与运维](docs/configuration.md)
- [插件开发](docs/plugin-development.md)
- [插件元数据与打包](docs/packaging.md)

本地检查不等于真实 QQ 平台验收；实际可用能力取决于账号权限和平台接口。运行诊断使用英文日志，原始响应以 `Raw response` 标记；翻译资源仍可提供中文输出。

