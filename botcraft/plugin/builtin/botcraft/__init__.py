"""Built-in administration commands using native MCDR nodes."""
from copy import deepcopy
from functools import partial
from mcdreforged.command.builder.nodes.basic import Literal
from mcdreforged.command.builder.nodes.arguments import Text, QuotableText
from mcdreforged.permission.permission_level import PermissionLevel
from botcraft.command.command_source import QQCommandSource, ConsoleSource
from botcraft.message.user import User


def register(server):
    runtime = server._runtime
    manager = runtime.permission_manager
    def tr(src, key, *args):
        return runtime.translation_manager.tr('botcraft.' + key, *args, language=src.get_preference().language)
    root = Literal('/botcraft')

    def allowed(src):
        return isinstance(src, ConsoleSource) or manager.is_super_admin(src)

    def help_command(src):
        lines = []
        for help_ in runtime.plugin_manager.registry_storage.help_messages:
            if src.has_permission(help_.permission) and (not isinstance(src, QQCommandSource) or src.scene in help_.scope):
                message = help_.message
                if isinstance(message, dict):
                    from mcdreforged.utils.translation_utils import translate_from_dict
                    from mcdreforged.translation.language_fallback_handler import LanguageFallbackHandler
                    message = translate_from_dict(message, src.get_preference().language, fallback_handler=LanguageFallbackHandler.auto())
                lines.append(f'{help_.prefix}: {message}')
        src.reply('\n'.join(lines) or tr(src, 'help.empty'))
    root.runs(help_command)
    root.then(Literal('help').runs(help_command))

    def choose_target(src, target=None):
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

    def permission_action(src, ctx, action):
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
                src.reply(tr(src, 'permission.set', target.id, level.name))
            elif action == 'remove':
                manager.remove_permission(target, global_scope=global_scope)
                src.reply(tr(src, 'permission.remove', target.id))
            else:
                if global_scope:
                    level = manager.get_player_permission_level(manager.encode_key(target, global_scope=True), auto_add=False)
                    src.reply(tr(src, 'permission.query_global', target.id, level))
                else:
                    src.reply(tr(src, 'permission.query', target.id, manager.get_permission(target)))
        except (ValueError, TypeError, KeyError) as error:
            src.reply(str(error))

    def scopes(node, action):
        node.runs(lambda src, ctx: permission_action(src, ctx, action))
        def flagged(flag, field):
            return Literal(flag).requires(lambda src, ctx: (ctx.__setitem__(field, True), True)[1]).redirects(node)
        node.then(flagged({'-g', '--global'}, 'global_scope'))
        node.then(flagged('--c2c', 'c2c'))
        group = Literal('--group')
        group.then(Text('group_id').redirects(node))
        node.then(group)
        return node

    perm = Literal({'permission', 'perm'}).requires(allowed)
    perm.runs(lambda src: src.reply('permission list [level] | set <id> <level> | query [id] | remove <id>; --group <id> / --c2c / -g'))
    def list_permission(src, ctx):
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
    def show_pref(src):
        src.reply(tr(src, 'preference.language', runtime.preference_manager.get_preference(src).language) + '; available: ' + ', '.join(sorted(runtime.translation_manager.available_languages)))
    pref.runs(show_pref).then(Literal('list').runs(show_pref))
    language = Literal('language').runs(show_pref)
    def set_language(src, value):
        if value is None:
            value = runtime.get_language()
        if value not in runtime.translation_manager.available_languages:
            src.reply(tr(src, 'preference.invalid_language', value))
            return
        item = runtime.preference_manager.get_preference(src)
        item.language = value
        runtime.preference_manager.set_preference(src, item)
        src.reply(tr(src, 'preference.set', value))
    language.then(Literal('set').then(QuotableText('value').suggests(lambda: runtime.translation_manager.available_languages).runs(lambda src, ctx: set_language(src, ctx['value']))))
    language.then(Literal('reset').runs(lambda src: set_language(src, None)))
    pref.then(language)
    root.then(pref)

    plugin = Literal('plugin').requires(allowed)
    plugin.then(Literal('list').runs(lambda src: src.reply('\n'.join(str(p.get_metadata()) for p in runtime.plugin_manager.get_all_plugins()))))
    for action in ('load', 'unload', 'reload'):
        def operate(src, ctx, *, action):
            result = getattr(server, action + '_plugin')(ctx['plugin'])
            src.reply(f'plugin {action}: {result}')
        plugin.then(Literal(action).then(QuotableText('plugin').runs(partial(operate, action=action))))
    plugin.then(Literal('refresh').runs(lambda src: server.refresh_all_plugins()))
    root.then(plugin)

    reload_node = Literal('reload').requires(allowed)
    def reload_part(src, *, part):
        if part == 'config':
            runtime.load_config(log=True)
        elif part == 'permission':
            runtime.permission_manager.load_permission_file(allowed_missing_file=False)
        else:
            runtime.preference_manager.load_preferences()
        src.reply(tr(src, 'reload.' + part))
    for part in ('config', 'permission', 'preference'):
        reload_node.then(Literal(part).runs(partial(reload_part, part=part)))
    root.then(reload_node)
    root.then(Literal('exit').requires(allowed).runs(lambda src: runtime.exit()))
    server.register_command(root)
    server.register_help_message('/botcraft', {
        language: runtime.translation_manager.tr('botcraft.help.description', language=language)
        for language in runtime.translation_manager.available_languages
    })
    runtime.builtin_command_root = root
    return root
