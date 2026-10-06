"""Built-in administration commands using native MCDR nodes."""
from copy import deepcopy
from functools import partial
from pathlib import Path
from mcdreforged.utils.string_utils import clean_minecraft_color_code
from typing import Any
from mcdreforged.command.builder.common import CommandContext
from mcdreforged.command.builder.nodes.basic import AbstractNode
from botcraft.plugin.si.plugin_server_interface import QQPluginServerInterface
from botcraft.message.qtext.text import QText, QMarkdown, QTextInput
from botcraft.constants.core_constant import VERSION
from botcraft.translation.translation_text import QQTranslationText
from botcraft.translation.translation_manager import TranslationParameter
from mcdreforged.command.builder.nodes.basic import Literal
from mcdreforged.command.builder.nodes.arguments import Text, QuotableText
from mcdreforged.permission.permission_level import PermissionLevel
from botcraft.command.command_source import QQCommandSource, ConsoleSource
from botcraft.message.user import User


def register(server: QQPluginServerInterface) -> Literal:
    """Register the built-in administration command tree.
    
    :param server: Bound interface of the built-in plugin.
    :return: Registered administration root.
    """
    runtime = server._runtime
    manager = runtime.permission_manager
    def tr(src: QQCommandSource | ConsoleSource, key: str, *args: TranslationParameter) -> str | QText | QMarkdown:
        """Translate validation feedback in the invoking source language.
        
        :param src: Invoking QQ or console source.
        :param key: BotCraft-relative translation key.
        :param args: Open translation formatting arguments.
        :return: Immediately localized validation feedback.
        """
        return runtime.translation_manager.tr('botcraft.' + key, *args, language=src.get_preference().language)

    def rtr(key: str, *args: TranslationParameter) -> QQTranslationText:
        """Create source-language-delayed BotCraft feedback.
        
        :param key: BotCraft-relative translation key.
        :param args: Open translation formatting arguments.
        :return: Translation evaluated by the reply recipient language.
        """
        return server.rtr('botcraft.' + key, *args)
    root = Literal('/botcraft')

    def allowed(src: QQCommandSource | ConsoleSource) -> bool:
        """Check access to administrative commands.
        
        :param src: Invoking QQ or console source.
        :return: Whether the source is console or a configured super administrator.
        """
        return isinstance(src, ConsoleSource) or manager.is_super_admin(src)
    def root_command(src: QQCommandSource | ConsoleSource) -> None:
        """Reply with the framework version and registered command help inputs.

        :param src: Invoking QQ or console source.
        :return: No value is returned.
        """
        message = QMarkdown(tr(src, 'help.version', VERSION))
        for help_ in runtime.plugin_manager.registry_storage.help_messages:
            if src.has_permission(help_.permission) and (not isinstance(src, QQCommandSource) or src.scene in help_.scope):
                description = help_.message
                if isinstance(description, dict):
                    from mcdreforged.utils.translation_utils import translate_from_dict
                    from mcdreforged.translation.language_fallback_handler import LanguageFallbackHandler
                    description = translate_from_dict(description, src.get_preference().language, fallback_handler=LanguageFallbackHandler.auto())
                description = runtime.translation_manager.evaluate(description, language=src.get_preference().language)
                message.append('\n', QTextInput(help_.prefix, show=help_.prefix), f' - {description}')
        src.reply(message)

    def help_command(src: QQCommandSource | ConsoleSource) -> None:
        """Reply with the built-in BotCraft command directory.

        :param src: Invoking QQ or console source.
        :return: No value is returned.
        """
        entries = (
            ('/botcraft help', 'help'),
            ('/botcraft perm', 'permission'),
            ('/botcraft plugin', 'plugin'),
            ('/botcraft pref', 'preference'),
            ('/botcraft reload', 'reload'),
            ('/botcraft exit', 'exit'),
        )
        message = QMarkdown(tr(src, 'help.title'))
        for command, key in entries:
            message.append('\n', QTextInput(command, show=command), ' - ', tr(src, 'help.command.' + key))
        src.reply(message)
    root.runs(root_command)
    root.then(Literal('help').runs(help_command))

    def choose_target(src: QQCommandSource | ConsoleSource, target: str | None = None) -> User:
        """Resolve an explicit, mentioned or invoking permission target.
        
        :param src: Invoking QQ or console source.
        :param target: Explicit user identifier, or None to use a mention or invoking user.
        :return: Independent target user with appropriate conversation scope.
        """
        mentions = src.message_data.mentions or [] if isinstance(src, QQCommandSource) else []
        if target and mentions or len(mentions) > 1:
            raise ValueError(tr(src, 'permission.ambiguity'))
        if mentions:
            user = deepcopy(mentions[0])
            user.scene, user.group_openid = src.scene, src.conversation if src.scene == 'group' else None
            return user
        if target:
            if isinstance(src, QQCommandSource) and src.scene == 'group':
                return User(id=target, scene='group', group_openid=src.conversation)
            known = runtime.users.get_user(target, scene='c2c')
            if known is None:
                raise ValueError(tr(src, 'permission.unknown_user'))
            return known
        if isinstance(src, QQCommandSource):
            return deepcopy(src.user)
        raise ValueError('Console commands require a known user ID')

    def permission_action(src: QQCommandSource | ConsoleSource, ctx: CommandContext | dict[str, Any], action: str) -> None:
        """Apply a permission command with its explicit scope.
        
        :param src: Invoking QQ or console source.
        :param ctx: Parsed permission arguments and scope flags.
        :param action: Permission operation to perform.
        :return: No value is returned.
        """
        try:
            target = choose_target(src, ctx.get('target'))
            group_id = ctx.get('group_id')
            c2c = ctx.get('c2c', False)
            global_scope = ctx.get('global_scope', False)
            if sum([group_id is not None, c2c, global_scope]) > 1:
                raise ValueError(tr(src, 'permission.scope_conflict'))
            if isinstance(src, ConsoleSource) and not any([group_id is not None, c2c, global_scope]):
                raise ValueError('Console commands require --group, --c2c or -g')
            if group_id is not None:
                target.scene, target.group_openid = 'group', group_id
            elif c2c:
                known = runtime.users.get_user(target.require_identity(), scene='c2c')
                if known is None:
                    raise ValueError(tr(src, 'permission.unknown_user'))
                target = known
            if action == 'set':
                level = PermissionLevel.from_value(ctx['level'])
                manager.set_permission(target, level, global_scope=global_scope)
                src.reply(rtr('permission.set', target.id, level.name))
            elif action == 'remove':
                manager.remove_permission(target, global_scope=global_scope)
                src.reply(rtr('permission.remove', target.id))
            else:
                if global_scope:
                    level = manager.get_player_permission_level(manager.encode_key(target, global_scope=True), auto_add=False)
                    src.reply(rtr('permission.query_global', target.id, level))
                else:
                    src.reply(rtr('permission.query', target.id, manager.get_permission(target)))
        except (ValueError, TypeError, KeyError) as error:
            src.reply(str(error))

    def scopes(node: AbstractNode, action: str) -> AbstractNode:
        """Attach supported permission scope flags to an argument node.
        
        :param node: Permission operation node.
        :param action: Permission operation to perform.
        :return: The operation node with scope branches registered.
        """
        node.runs(lambda src, ctx: permission_action(src, ctx, action))
        def flagged(flag: str | set[str], field: str) -> Literal:
            """Build a permission scope flag that redirects to its operation.
            
            :param flag: Literal flag or aliases.
            :param field: Context field marked by the flag.
            :return: Flag node redirecting to the operation.
            """
            return Literal(flag).requires(lambda src, ctx: (ctx.__setitem__(field, True), True)[1]).redirects(node)
        node.then(flagged({'-g', '--global'}, 'global_scope'))
        node.then(flagged('--c2c', 'c2c'))
        group = Literal('--group')
        group.then(Text('group_id').redirects(node))
        node.then(group)
        return node

    perm = Literal({'permission', 'perm'}).requires(allowed)
    perm.runs(lambda src: src.reply('permission list [level] | set <id> <level> | query [id] | remove <id>; --group <id> / --c2c / -g'))
    def list_permission(src: QQCommandSource | ConsoleSource, ctx: CommandContext | dict[str, Any]) -> None:
        """Reply with users belonging to the selected permission levels.
        
        :param src: Invoking QQ or console source.
        :param ctx: Optional permission level argument.
        :return: No value is returned.
        """
        levels = [PermissionLevel.from_value(ctx['level'])] if 'level' in ctx else PermissionLevel.INSTANCES
        src.reply('\n'.join(f'{lv.name}: {manager.get_permission_group_list(lv.name)}' for lv in levels))
    perm.then(Literal('list').runs(lambda src: list_permission(src, {})).then(Text('level').runs(list_permission)))
    for action, aliases in [('set', {'set'}), ('query', {'query', 'q'}), ('remove', {'remove', 'rm'})]:
        branch = Literal(aliases)
        if action == 'query':
            scopes(branch, action)
        elif action == 'remove':
            scopes(branch, action)
        if action == 'set':
            branch.then(scopes(Text('level'), action))
            target_node = Text('target')
            target_node.then(scopes(Text('level'), action))
            branch.then(target_node)
        else:
            branch.then(scopes(Text('target'), action))
        perm.then(branch)
    root.then(perm)

    pref = Literal({'preference', 'pref'})
    def show_pref(src: QQCommandSource | ConsoleSource) -> None:
        """Reply with the active language and available languages.
        
        :param src: Invoking QQ or console source.
        :return: No value is returned.
        """
        src.reply(rtr('preference.language', runtime.preference_manager.get_preference(src).language) + '; available: ' + ', '.join(sorted(runtime.translation_manager.available_languages)))
    pref.runs(show_pref).then(Literal('list').runs(show_pref))
    language = Literal('language').runs(show_pref)
    def set_language(src: QQCommandSource | ConsoleSource, value: str | None) -> None:
        """Persist a selected source language or reset to runtime language.
        
        :param src: Invoking QQ or console source.
        :param value: Requested language, or None to reset.
        :return: No value is returned.
        """
        if value is None:
            value = runtime.get_language()
        if value not in runtime.translation_manager.available_languages:
            src.reply(rtr('preference.invalid_language', value))
            return
        item = runtime.preference_manager.get_preference(src)
        item.language = value
        runtime.preference_manager.set_preference(src, item)
        src.reply(rtr('preference.set', value))
    language.then(Literal('set').then(QuotableText('value').suggests(lambda: runtime.translation_manager.available_languages).runs(lambda src, ctx: set_language(src, ctx['value']))))
    language.then(Literal('reset').runs(lambda src: set_language(src, None)))
    pref.then(language)
    root.then(pref)

    plugin = Literal('plugin').requires(allowed)
    def list_plugins(src: QQCommandSource | ConsoleSource) -> None:
        """Reply once with loaded, disabled and unloaded plugin groups.
        
        :param src: Invoking QQ or console source.
        :return: No value is returned.
        """
        current_plugins = list(runtime.plugin_manager.get_all_plugins())
        disabled_plugins = server.get_disabled_plugin_list()
        unloaded_plugins = server.get_unloaded_plugin_list()
        message = server.rtr('mcdreforged.mcdr_command.list_plugin.info_loaded_plugin', len(current_plugins))
        for current in current_plugins:
            message.append(f'\n- {current.get_metadata().name} ({current.get_identifier()})')
        message.append('\n', server.rtr('mcdreforged.mcdr_command.list_plugin.info_disabled_plugin', len(disabled_plugins)))
        for file_path in disabled_plugins:
            message.append(f'\n- {Path(file_path).name}')
        message.append('\n', server.rtr('mcdreforged.mcdr_command.list_plugin.info_not_loaded_plugin', len(unloaded_plugins)))
        for file_path in unloaded_plugins:
            message.append(f'\n- {Path(file_path).name}')
        evaluated = runtime.translation_manager.evaluate(message, language=src.get_preference().language)
        src.reply(QText(clean_minecraft_color_code(evaluated.to_plain_text())))

    plugin.then(Literal('list').runs(list_plugins))
    for action in ('load', 'unload', 'reload'):
        def operate(src: QQCommandSource | ConsoleSource, ctx: CommandContext, *, action: str) -> None:
            """Apply a native plugin operation and reply with its result.
            
            :param src: Invoking QQ or console source.
            :param ctx: Parsed plugin identifier or path.
            :param action: Native plugin operation to invoke.
            :return: No value is returned.
            """
            result = getattr(server, action + '_plugin')(ctx['plugin'])
            src.reply(f'plugin {action}: {result}')
        argument = QuotableText('plugin')
        if action in ('unload', 'reload'):
            argument.suggests(server.get_plugin_list)
        plugin.then(Literal(action).then(argument.runs(partial(operate, action=action))))
    plugin.then(Literal('refresh').runs(lambda src: server.refresh_all_plugins()))
    root.then(plugin)

    reload_node = Literal('reload').requires(allowed)
    def reload_part(src: QQCommandSource | ConsoleSource, *, part: str) -> None:
        """Reload the selected administration configuration component.
        
        :param src: Invoking QQ or console source.
        :param part: Configuration, permission or preference component.
        :return: No value is returned.
        """
        if part == 'config':
            runtime.load_config(log=True)
        elif part == 'permission':
            runtime.permission_manager.load_permission_file(allowed_missing_file=False)
        else:
            runtime.preference_manager.load_preferences()
        src.reply(rtr('reload.' + part))
    for part in ('config', 'permission', 'preference'):
        reload_node.then(Literal(part).runs(partial(reload_part, part=part)))
    root.then(reload_node)
    root.then(Literal('exit').requires(allowed).runs(lambda src: runtime.exit()))
    server.register_command(root)
    server.register_help_message('/botcraft', server.rtr('botcraft.help.description'))
    runtime.builtin_command_root = root
    return root
