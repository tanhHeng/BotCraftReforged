# 插件元数据与打包

[文档目录](README.md) · [插件开发](plugin-development.md)

## 支持的插件格式

| 格式 | 元数据与入口 | 使用方式 |
| --- | --- | --- |
| 单文件 `.py` | 模块级 `PLUGIN_METADATA` 字典 | 放入实例插件目录，框架发现并加载文件。 |
| 目录插件 | 根目录的 `botcraft.plugin.json`，`entrypoint` 指向 Python 模块/包 | 将完整插件目录放入实例插件目录。 |
| `.mcdr` / `.pyz` 压缩插件 | 压缩包根目录的 `botcraft.plugin.json` 和入口模块 | 由 `botcraft pack` 生成，再放入实例插件目录。 |

默认插件目录是实例的 `plugins/`，可通过 `plugin_directories` 修改。`.mcdr` 与 `.pyz` 使用相同插件归档约定；即使加了 shebang，它们仍是交给 BotCraft 加载的插件，不是自动包含框架和凭据的独立机器人发行包。

单文件的实际用法见 [Echo 示例](../example_plugins/echo.py)。目录插件示例：

```text
example/
├── botcraft.plugin.json
├── echo_plugin/
│   └── __init__.py
├── requirements.txt
└── assets/
    └── help.txt
```

`requirements.txt` 和资源目录均可省略。`echo_plugin/__init__.py` 放置插件回调；若把开发指南的单文件代码迁入目录插件，使用 JSON 元数据作为唯一元数据来源，不再需要该文件的 `PLUGIN_METADATA`。

## 元数据

`botcraft.plugin.json` 使用 MCDR Metadata 格式，但文件名属于 BotCraft：

```json
{
  "id": "echo_plugin",
  "version": "1.0.0",
  "name": "Echo",
  "description": "Reply with the supplied text",
  "entrypoint": "echo_plugin",
  "dependencies": {
    "botcraft": ">=0.1.0"
  },
  "resources": ["assets"],
  "archive_name": "{id}-v{version}"
}
```

常用字段：

| 字段 | 含义 |
| --- | --- |
| `id` | 插件唯一 ID，也用于依赖关系、运维命令和 `config/<id>` 数据目录。使用稳定 ID，避免与其他插件冲突。 |
| `version` | 插件版本；框架按照元数据版本约束处理依赖。 |
| `name` | 展示名称。 |
| `description` | 展示描述，支持字符串或语言字典；普通硬编码文本使用英文，多语言用户反馈通过翻译键提供。 |
| `entrypoint` | 目录/压缩插件的 Python 入口模块名。 |
| `dependencies` | 插件 ID 到版本约束；框架自身的 ID 是 `botcraft`，不是 `mcdr`。这不是 pip 依赖列表。 |
| `resources` | 要随插件归档分发的资源目录列表。 |
| `archive_name` | 默认归档文件名模板，可使用 `{id}`、`{version}`。 |

Python 第三方库写在 `requirements.txt`，分发前安排安装到运行实例使用的 Python 环境中。框架加载时会检查要求，不应把插件加载当作第三方依赖自动安装器。

入口模块、Python 依赖和资源需要在实际部署环境中可用。只读打包资源使用 `server.open_bundled_file('assets/help.txt')`；可写状态存入 `server.get_data_folder()`，不要写进插件归档。

## 打包命令

在包含 `example/` 的工作目录执行：

```sh
botcraft pack -i example -o packed_plugins
botcraft pack -i example -o packed_plugins -n "{id}-{version}.pyz" --ignore-patterns "__pycache__/" "*.pyc"
botcraft pack -i example -o packed_plugins --ignore-file .gitignore --shebang "/usr/bin/env python3"
```

- 输入必须是带有 `botcraft.plugin.json` 的目录；不直接打包单个 `.py` 文件。
- `-o` 指定输出目录，`-n` 覆盖默认文件名模板。确认实际输出文件名后再复制，不假设示例固定生成某个扩展名。
- 忽略规则使用 gitignore 风格，相对插件输入目录匹配。`--ignore-patterns` 覆盖 `--ignore-file`。
- 默认忽略文件是输入目录的 `.gitignore`；缺少忽略文件时可以打包，但要自行检查归档是否包含缓存、凭据或开发文件。
- `--shebang` 设置可选解释器行。框架沿用 MCDR 2.14.4 的资源、requirements 和归档约定，不需要修改 MCDR 安装文件。

将实际生成的 `.mcdr` 或 `.pyz` 放入实例配置的插件目录，正常启动或执行 `/botcraft plugin refresh`，再用 `/botcraft plugin list` 确认加载。修改后可执行 `/botcraft plugin reload echo_plugin`；加载失败时检查日志中的元数据、依赖和入口导入错误。

开发源码中单文件插件、目录插件和压缩插件不要同时保留相同 ID 的可加载副本。BotCraft 插件与 Minecraft 插件共享部分打包格式，不共享 Minecraft 输入/宿主 API；迁移前阅读[QQ-only 差异](plugin-development.md#与-mcdr-插件的差异)。
