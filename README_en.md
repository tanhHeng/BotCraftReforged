# BotCraftReforged

[中文](README.md) | **English**

> A framework for developing official QQ bots, built on [MCDReforged](https://github.com/MCDReforged/MCDReforged).

BotCraftReforged builds on MCDR's plugin development, command management, permission management, and other capabilities. You can develop BotCraft plugins much like MCDR plugins, using message and event interfaces designed for QQ.

“Reforged” describes BotCraft as a reforging of MCDR and expresses our appreciation for MCDR's design. The distribution name, Python import namespace, and command-line entry point are all `botcraft`.

## Features

- Runs independently using the official QQ bot Gateway and HTTP API, supporting group chats and C2C.
- Reuses MCDR's plugin lifecycle, command trees, permissions, and translations.
- Provides QQ interfaces for passive replies, text, Markdown, keyboards, and command panels.
- Supports single-file, directory, and packed plugins for development and distribution.

Requires **Python 3.10 or later**. MCDR 2.14.4 is a code dependency, not the runtime host; no Minecraft server is required.

## Getting started

The project has not yet been published to PyPI. Install from the source directory:

```sh
python -m pip install .
botcraft --version
```

Then initialize an instance in a separate, empty directory:

```sh
mkdir botcraft-run
cd botcraft-run
botcraft init
```

Enter your QQ Open Platform `appid` and `secret` in the generated `config.yml`, then start the bot:

```sh
botcraft start
```

You can also use `python -m botcraft`; running without arguments is equivalent to `start`. Initialization creates missing files without overwriting existing ones. See [Deployment and configuration](docs/configuration.md) for configuration and administration commands.

## Plugins

Place plugins in the instance's `plugins` directory. Start with the [Echo example](example_plugins/echo.py): send `/echo Hello world` in a group chat or C2C conversation to receive a passive reply using the original message context.

The [Plugin development guide](docs/plugin-development.md) covers commands, events, permissions, translations, and QQ messages. The [Packaging guide](docs/packaging.md) covers plugin formats and distribution.

## Documentation

The detailed guides are currently available in Simplified Chinese:

- [Documentation index and development checks](docs/README.md)
- [Deployment, configuration, logging, and administration](docs/configuration.md)
- [Plugin development](docs/plugin-development.md)
- [Plugin metadata and packaging](docs/packaging.md)

Local checks do not constitute acceptance testing against the real QQ platform. Available capabilities depend on account permissions and platform APIs. Runtime diagnostics use English log messages, with raw responses marked `Raw response`; translation resources can still provide Chinese output.
