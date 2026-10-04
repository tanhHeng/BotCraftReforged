"""Isolated, consumer-visible checks shipped with the installed library.

Run with ``python -m botcraft.compatibility.probes``. This is a local runtime
check, not acceptance of credentials, QQ networking, menus or Minecraft.
"""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import traceback
from zipfile import ZipFile


_REPORT_PREFIX = 'BOTCRAFT_CAPABILITY_REPORT='
_TIMEOUT = 20


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def rejects(error_types, operation, message):
    try:
        operation()
    except error_types:
        return
    raise AssertionError(message)


def _journal():
    path = Path('probe-journal.jsonl')
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines()] if path.exists() else []


def _plugin_code(identity, *, solo=False, decorated=False):
    metadata = "PLUGIN_METADATA = " + repr({'id': identity, 'version': '1.0.0', 'name': 'Capability ' + identity}) + '\n' if solo else ''
    decoration = '''
from botcraft.api.decorator import event_listener

@event_listener('capability.priority', priority=10)
def early(server):
    record('priority', 'early', QQServerInterface.psi().get_self_metadata().id)
''' if decorated else ''
    return metadata + '''
import json
from pathlib import Path
from threading import Event
from mcdreforged.command.builder.nodes.basic import Literal
from mcdreforged.command.builder.nodes.arguments import Integer
from botcraft.plugin.si.server_interface import QQServerInterface

generation = 0
async_complete = Event()
message_complete = Event()

def record(kind, *values):
    with Path('probe-journal.jsonl').open('a', encoding='utf8') as stream:
        stream.write(json.dumps([kind, *values]) + '\\n')

def command(source, context):
    record('command', QQServerInterface.psi().get_self_metadata().id, context['amount'], source.scene)

def late(server):
    record('priority', 'late', QQServerInterface.psi().get_self_metadata().id)

async def async_listener(server):
    import asyncio
    before = QQServerInterface.psi().get_self_metadata().id
    await asyncio.sleep(0)
    record('async-listener', before, QQServerInterface.psi().get_self_metadata().id)
    async_complete.set()

def on_message(server, event):
    if server.get_self_metadata().id == 'cap_solo':
        record('message', event.message_data.author.id, event.get_command_source().conversation,
               QQServerInterface.psi().get_self_metadata().id)
        message_complete.set()

def on_load(server, old):
    global generation
    identity = server.get_self_metadata().id
    generation = 1 if old is None else old.generation + 1
    record('load', identity, generation, QQServerInterface.psi().get_self_metadata().id)
    server.register_translation('en_us', {identity: {'format': 'Hello {0}', 'repeated': '{0}/{0}', 'pair': '{0}/{1}'}})
    server.register_translation('zh_cn', {identity: {'format': 'Localized hello {0}'}})
    record('immediate', identity, server.tr(identity + '.format', 'world', language='en_us', allow_failure=False))
    server.register_help_message('!!' + identity, 'Capability command', permission=2, scope=('group',))
    server.register_command(Literal('!!' + identity).requires(lambda source: source.has_permission(2)).then(Integer('amount').runs(command)), scope=('group',))
    if identity == 'cap_solo':
        server.register_event_listener('capability.priority', late, priority=90)
        server.register_event_listener('capability.async', async_listener)

def on_unload(server):
    record('unload', server.get_self_metadata().id)
''' + decoration


def _write_fixtures():
    paths = {'cap_solo': Path('plugins/cap_solo.py'),
             'cap_directory': Path('plugins/cap_directory'),
             'cap_packed': Path('plugins/cap_packed.mcdr')}
    paths['cap_solo'].write_text(_plugin_code('cap_solo', solo=True, decorated=True), encoding='utf8')
    for identity, dependency in [('cap_directory', 'cap_solo'), ('cap_packed', 'cap_directory')]:
        metadata = json.dumps({'id': identity, 'version': '1.0.0', 'name': 'Capability ' + identity,
                               'entrypoint': identity, 'dependencies': {dependency: '>=1.0.0'}})
        if identity == 'cap_directory':
            root = paths[identity]
            (root / identity).mkdir(parents=True)
            (root / 'botcraft.plugin.json').write_text(metadata, encoding='utf8')
            (root / identity / '__init__.py').write_text(_plugin_code(identity), encoding='utf8')
        else:
            with ZipFile(paths[identity], 'w') as archive:
                archive.writestr('botcraft.plugin.json', metadata)
                archive.writestr(identity + '/__init__.py', _plugin_code(identity))
    return paths


def _prepare():
    from ruamel.yaml import YAML
    from botcraft.config import load_resource_yaml
    Path('plugins').mkdir()
    Path('config/botcraft').mkdir(parents=True)
    Path('logs').mkdir()
    config = load_resource_yaml('resources/default_config.yml')
    config.update(appid='capability-local', secret='not-a-network-credential', advanced_console=False,
                  disable_console_thread=True, plugin_directories=['plugins'])
    with Path('config.yml').open('w', encoding='utf8') as stream:
        YAML().dump(config, stream)
    with Path('permissions.yml').open('w', encoding='utf8') as stream:
        YAML().dump(load_resource_yaml('resources/default_permission.yml'), stream)
    return _write_fixtures()


def _source(runtime, *, scene='group', role='member', identity='official-user'):
    from botcraft.event.event_parser import EventParser
    author = {'id': identity, 'member_role': role}
    data = {'id': 'received-' + scene, 'author': author, 'content': 'capability', 'message_type': 0,
            'timestamp': datetime.now(timezone.utc).isoformat(), 'message_scene': {'ext': ['original-index']}}
    if scene == 'group':
        author['member_openid'] = 'member-route'
        data['group_openid'] = 'group-route'
    else:
        author['user_openid'] = 'private-route'
    payload = {'op': 0, 't': 'C2C_MESSAGE_CREATE' if scene == 'c2c' else 'GROUP_AT_MESSAGE_CREATE',
               's': 1, 'id': 'event-' + scene, 'd': data}
    received = EventParser(runtime).parse(payload)
    return received.get_command_source(), received, payload


def _config_permissions(runtime):
    from ruamel.yaml import YAML
    from mcdreforged.preference.preference_manager import PreferenceItem
    from botcraft.config import ConfigManager
    from botcraft.message.user import User
    from botcraft.permission.permission_manager import PermissionManager

    manager = runtime.config_manager
    manager.set_values({'http.timeout': 3.0, 'permission.mode': 'role'})
    manager.save()
    disk_manager = ConfigManager(runtime.logger, 'config.yml')
    disk_manager.load()
    require(disk_manager.get_config().http.timeout == 3.0, 'Configuration write/read lost timeout')
    require(disk_manager.get_config().permission.mode == 'role', 'Configuration write/read lost permission mode')
    manager.set_values({'http.timeout': 8.0})
    runtime.load_config()
    require(runtime.get_config().http.timeout == 3.0, 'Runtime reload did not apply the bound configuration file')
    before = manager.get_config().serialize()
    valid_file = Path('config.yml').read_bytes()
    invalid = YAML(typ='safe').load(valid_file.decode('utf8'))
    invalid['gateway']['intents'] = ['UNSUPPORTED_INTENT']
    with Path('config.yml').open('w', encoding='utf8') as stream:
        YAML().dump(invalid, stream)
    rejected_file = Path('config.yml').read_bytes()
    rejects(ValueError, runtime.load_config, 'Invalid configuration reload was accepted')
    require(manager.get_config().serialize() == before, 'Rejected reload changed active configuration')
    require(Path('config.yml').read_bytes() == rejected_file, 'Rejected reload overwrote the rejected file')
    Path('config.yml').write_bytes(valid_file)
    rejects(ValueError, lambda: manager.set_values({'secret': 'changed'}), 'Hot credential changes were accepted')
    require(manager.get_config().serialize() == before, 'Rejected hot credentials changed active configuration')

    owner = User(id='same-user', scene='group', group_openid='group-a', member_role='owner')
    other_group = User(id='same-user', scene='group', group_openid='group-b', member_role='owner')
    private = User(id='same-user', scene='c2c', user_openid='private-route')
    runtime.users.record(private)
    permissions = runtime.permission_manager
    require(permissions.get_permission(owner) == 4, 'Group owner role did not map to level 4')
    require(permissions.get_permission(private) == 0, 'Unconfigured C2C permission was not zero')
    permissions.set_permission(owner, 0)
    permissions.set_permission(private, 2, global_scope=True)
    require(permissions.get_permission(owner) == 0, 'Explicit zero did not override global/role permission')
    require(permissions.get_permission(other_group) == 2, 'Global permission did not apply to another conversation')
    restored = PermissionManager(runtime, 'permissions.yml')
    restored.load_permission_file()
    require(restored.get_permission(owner) == 0 and restored.get_permission(private) == 2,
            'Permission storage roundtrip changed scoped zero or global permission')
    permissions.remove_permission(owner)
    require(permissions.get_permission(owner) == 2, 'Removing scoped permission did not restore global precedence')
    permissions.remove_permission(private, global_scope=True)
    require(permissions.get_permission(owner) == 4, 'Removing global permission did not restore role permission')
    manager.set_values({'permission.mode': 'native'})
    require(permissions.get_permission(owner) == 0, 'Native permission mode used group role')
    manager.set_values({'permission.mode': 'mixed', 'permission.super_admins': ['same-user']})
    permissions.set_permission(owner, 0)
    require(permissions.get_permission(owner) == 4, 'Super administrator did not override explicit zero')
    manager.set_values({'permission.super_admins': []})

    subject = User(id='preference-user', scene='c2c', user_openid='preference-route')
    preferences = runtime.preference_manager
    supplied = PreferenceItem(language='en_us')
    preferences.set_preference(subject, supplied)
    supplied.language = 'zh_cn'
    result = preferences.get_preference(subject)
    require(result.language == 'en_us', 'Preference setting retained caller-owned mutable item')
    result.language = 'zh_cn'
    preferences.load_preferences()
    require(preferences.get_preference(subject).language == 'en_us', 'Preference copies or storage changed the saved language')
    untouched = User(id='unrecorded', scene='c2c', user_openid='unrecorded-route')
    preferences.get_preference(untouched)
    require('unrecorded' not in json.loads(Path('config/botcraft/preferences.json').read_text(encoding='utf8')),
            'Default preference lookup inserted a persistent record')


def _text_models(runtime):
    from botcraft.message.qtext.keyboard import (
        QKeyboardTemplate, QKeyboardPermission, QKeyboardPermissionType, QKeyboardCustom,
        QKeyboardButton, QKeyboardRenderData, QKeyboardActionCallback, QKeyboardModal,
    )
    from botcraft.message.qtext.text import QText, QMarkdown
    from botcraft.message.message_data import QQMessageReceivedData, MessageType
    from botcraft.message.message_receipt import QQMessageReceipt
    from botcraft.message.user import Scene, MemberRole

    keyboard = QKeyboardTemplate('template-a')
    text = QText('before', keyboard=keyboard)
    snapshot = text.to_payload()
    rejects(ValueError, lambda: text.append('partial', QText('duplicate', keyboard=QKeyboardTemplate('template-b'))),
            'Multiple keyboards were combined')
    require(text.to_payload() == snapshot, 'Failed append partially changed text or keyboard')
    copied = text.copy()
    copied.get_keyboard().set_id('template-copy')
    copied.append('-copy')
    require(text.to_payload() == snapshot and copied.to_plain_text() == 'before-copy', 'Text copy shared mutable body/keyboard')
    promoted = QText('*literal*') + QMarkdown('**markup**', keyboard=keyboard)
    require(isinstance(promoted, QMarkdown) and promoted.to_payload()['markdown']['content'] == r'\*literal\***markup**',
            'Markdown promotion did not escape plain text while preserving Markdown')
    permission = QKeyboardPermission(QKeyboardPermissionType.SPECIFY, ['user-a'])
    before_permission = permission.to_payload()
    rejects(ValueError, lambda: permission.set_specify_user_ids([]), 'Empty SPECIFY keyboard users were accepted')
    require(permission.to_payload() == before_permission, 'Failed keyboard setter partially changed payload')
    custom = QKeyboardCustom([[QKeyboardButton(id='button-a',
        render_data=QKeyboardRenderData(label='Run', style=1),
        action=QKeyboardActionCallback(data='run', permission=QKeyboardPermission(), enter=False,
                                      anchor=0, modal=QKeyboardModal(content='Run now?', confirm_text='yes'))) ]])
    expected = {'content': {'rows': [{'buttons': [{'id': 'button-a', 'render_data': {'label': 'Run', 'style': 1},
        'action': {'type': 1, 'permission': {'type': 2}, 'data': 'run', 'enter': False, 'anchor': 0,
                   'modal': {'content': 'Run now?', 'confirm_text': 'yes'}}}]}]}}
    require(custom.to_payload() == expected, 'Custom keyboard lost official nested fields, false or zero')
    custom_copy = custom.copy()
    custom_copy.rows[0][0].action.set_data('changed')
    require(custom.to_payload() == expected, 'Custom keyboard copy shared nested action state')
    rejects(ValueError, lambda: custom.set_rows([[custom.rows[0][0], custom.rows[0][0]]]),
            'Duplicate keyboard button IDs were accepted')
    require(custom.to_payload() == expected, 'Rejected keyboard rows replaced the valid keyboard')
    payload = {'id': 'model-message', 'author': {'id': 'model-user', 'scene': 'group', 'member_role': 'admin'},
               'message_type': 103, 'msg_elements': [{'message_type': 102, 'msg_elements': [
                   {'message_type': 0, 'content': 'nested', 'attachments': [{'content_type': 'image/png', 'url': 'https://example.invalid/p.png'}]}]}]}
    model = QQMessageReceivedData.deserialize(payload)
    require(model.message_type is MessageType.REFERENCE and model.author.scene is Scene.GROUP
            and model.author.member_role is MemberRole.ADMIN, 'Protocol scalar enums did not become typed members')
    require(model.msg_elements[0].msg_elements[0].message_type is MessageType.TEXT, 'Recursive message parsing lost nested enum')
    require(model.serialize() == QQMessageReceivedData.deserialize(model.serialize()).serialize(), 'Recursive model protocol roundtrip changed values')
    clone = model.copy()
    clone.msg_elements[0].msg_elements[0].content = 'changed'
    clone.author.id = 'changed'
    require(model.msg_elements[0].msg_elements[0].content == 'nested' and model.author.id == 'model-user', 'Serializable copy aliased nested models')
    require(model.serialize()['message_type'] == 103 and model.serialize()['author']['member_role'] == 'admin', 'Enum serialization used member names instead of QQ values')
    unknown = QQMessageReceivedData.deserialize({'message_type': 987})
    require(unknown.serialize()['message_type'] == 987, 'Unknown protocol value was destroyed')
    rejects((TypeError, ValueError), lambda: QQMessageReceivedData.deserialize({'message_type': True}), 'Boolean was accepted as QQ integer enum')

    raw_response = {'id': 'sent-message', 'timestamp': datetime.now(timezone.utc).isoformat(), 'ext_info': {'ref_idx': 'reference'}}
    receipt = QQMessageReceipt(raw_response, 'group', 'submitted-group')
    raw_response['ext_info']['ref_idx'] = 'external-change'
    receipt.receipt_data.ext_info.ref_idx = 'model-change'
    require(receipt.raw_response['ext_info']['ref_idx'] == 'reference' and receipt.conversation == 'submitted-group',
            'Receipt lost raw response or submitted route isolation')
    source, received, raw = _source(runtime, role='admin')
    raw['d']['author']['id'] = 'external-change'
    received.message_data.author.id = 'model-change'
    received.message_data.author.member_role = 'owner'
    received.message_data.group_openid = 'model-group'
    require(source.user.id == 'official-user' and source.user.member_role is MemberRole.ADMIN
            and source.conversation == 'group-route' and source.msg_id == 'received-group',
            'Command source followed mutable parsed or caller-owned routing facts')
    require(received.raw_payload['d']['author']['id'] == 'official-user', 'Received raw envelope aliased caller payload')
    require(runtime.permission_manager.get_permission(source) == 2, 'Mutated message model changed the source role permission')
    source.user.id = 'source-change'
    require(received.original_user.id == 'official-user', 'Command source user aliased the received original author')
    private_source, private_message, _ = _source(runtime, scene='c2c', identity='private-official-id')
    require(private_source.user.id == 'private-official-id' and private_source.conversation == 'private-route',
            'C2C source collapsed distinct official identity and route OpenID')
    private_message.message_data.author.user_openid = 'model-route-change'
    require(private_source.conversation == 'private-route', 'C2C source followed mutated model routing')


def _translations(runtime):
    from botcraft.message.qtext.text import QText, QMarkdown
    from botcraft.message.qtext.keyboard import QKeyboardTemplate
    translator = runtime.translation_manager
    require(translator.tr('cap_solo.format', 'world', language='en_us', allow_failure=False) == 'Hello world', 'Plugin translation lookup failed')
    markdown = translator.tr('cap_solo.format', QMarkdown('**rich**'), language='en_us', allow_failure=False)
    require(isinstance(markdown, QMarkdown) and markdown.text == 'Hello **rich**', 'Translation destroyed Markdown argument')
    mixed = translator.tr('cap_solo.pair', QMarkdown('**rich**'), QText('*plain*'), language='en_us', allow_failure=False)
    require(isinstance(mixed, QMarkdown) and mixed.text == r'**rich**/\*plain\*', 'Translation did not escape plain text in Markdown')
    keyboard_argument = QText('button', keyboard=QKeyboardTemplate('translation-keyboard'))
    repeated = translator.tr('cap_solo.repeated', keyboard_argument, language='en_us', allow_failure=False)
    require(repeated.to_payload() == {'msg_type': 0, 'content': 'button/button', 'keyboard': {'id': 'translation-keyboard'}},
            'Repeated actual argument duplicated/dropped its keyboard')
    repeated.get_keyboard().set_id('changed')
    require(keyboard_argument.get_keyboard().id == 'translation-keyboard', 'Translation result aliased input keyboard')
    rejects(ValueError, lambda: translator.tr('cap_solo.pair', keyboard_argument, keyboard_argument.copy(), language='en_us'),
            'Distinct translated arguments accepted multiple keyboards')
    lazy = translator.rtr('cap_solo.format', QText('deferred'))
    repeated_lazy = translator.rtr('cap_solo.pair', keyboard_argument, keyboard_argument)
    lazy_copy = repeated_lazy.copy()
    require(translator.evaluate(lazy_copy, language='en_us').to_payload() == {
        'msg_type': 0, 'content': 'button/button', 'keyboard': {'id': 'translation-keyboard'}},
        'Deferred translation copy lost repeated argument identity or keyboard')
    with translator.language_context('en_us'):
        with translator.language_context('zh_cn'):
            require(translator.tr('cap_solo.format', 'nested', allow_failure=False) == 'Localized hello nested',
                    'Inner language scope did not change translation selection')
        evaluated = translator.evaluate(lazy)
    require(isinstance(evaluated, QText) and evaluated.text == 'Hello deferred', 'Deferred translation or nested language restoration failed')
    promoted_lazy = QText('*prefix*') + translator.rtr('cap_solo.format', QMarkdown('**deferred**'))
    promoted_result = translator.evaluate(promoted_lazy, language='en_us')
    require(isinstance(promoted_result, QMarkdown) and promoted_result.text == r'\*prefix\*Hello **deferred**',
            'Lazy translation concatenation lost Markdown promotion or escaped plain prefix')


def _plugin_registry_commands(runtime, paths):
    from mcdreforged.plugin.operation_result import PluginResultType
    from botcraft.plugin.plugin_event import LiteralEvent
    from botcraft.plugin.si.server_interface import QQServerInterface
    from botcraft.utils.exception import RuntimeNotReadyError
    manager = runtime.plugin_manager
    identities = ['cap_solo', 'cap_directory', 'cap_packed']
    records = [manager.get_plugin_from_id(identity) for identity in identities]
    require(all(record is not None for record in records), 'Not all three file plugin formats were loaded')
    for identity, record in zip(identities, records):
        require(record.get_metadata().id == identity and str(record.get_metadata().version) == '1.0.0', 'File plugin metadata did not match its own format')
    loads = [row[1] for row in _journal() if row[0] == 'load']
    require(loads == identities, 'Dependency ordering did not load providers before dependents')
    require([row for row in _journal() if row[0] == 'immediate'] == [
        ['immediate', identity, 'Hello world'] for identity in identities], 'Registered translations were not visible during on_load')
    help_messages = manager.registry_storage.help_messages
    require({item.prefix for item in help_messages if item.plugin in records} == {'!!' + identity for identity in identities},
            'Aggregated help lost file plugin registrations')
    manager.dispatch_event(LiteralEvent('capability.priority'), (), block=True)
    require([row for row in _journal() if row[0] == 'priority'] == [['priority', 'early', 'cap_solo'], ['priority', 'late', 'cap_solo']],
            'Decorated/declarative listener priority or plugin context failed')
    manager.dispatch_event(LiteralEvent('capability.async'), (), block=True)
    require(records[0].entry_module_instance.async_complete.wait(_TIMEOUT), 'Async listener did not complete')
    require(['async-listener', 'cap_solo', 'cap_solo'] in _journal(), 'Async listener lost its plugin context across await')
    _, _, inbound = _source(runtime, scene='c2c', identity='dispatched-official-id')
    runtime.event_dispatcher.submit_payload(inbound).result(timeout=_TIMEOUT)
    require(records[0].entry_module_instance.message_complete.wait(_TIMEOUT), 'Incoming message lifecycle listener did not run')
    require(['message', 'dispatched-official-id', 'private-route', 'cap_solo'] in _journal(),
            'Actual event dispatch lost parsed official identity, route or plugin context')
    require(runtime.users.get_user('dispatched-official-id', scene='c2c').user_openid == 'private-route',
            'Actual event dispatch did not retain distinct C2C official identity and routing OpenID')

    group, _, _ = _source(runtime)
    runtime.permission_manager.set_permission(group, 2)
    runtime.command_manager.execute_command('!!cap_solo 7', group)
    require([row for row in _journal() if row[0] == 'command'] == [['command', 'cap_solo', 7, 'group']],
            'Native Literal/Integer command parsing, execution or plugin context failed')
    runtime.permission_manager.set_permission(group, 0)
    try:
        runtime.command_manager.execute_command('!!cap_solo 8', group)
    except RuntimeNotReadyError:
        pass  # Native permission feedback attempts a real reply, forbidden locally.
    private, _, _ = _source(runtime, scene='c2c')
    runtime.users.record(private.user)
    runtime.permission_manager.set_permission(private, 3)
    try:
        runtime.command_manager.execute_command('!!cap_solo 9', private)
    except RuntimeNotReadyError:
        pass
    require([row for row in _journal() if row[0] == 'command'] == [['command', 'cap_solo', 7, 'group']],
            'Denied requires or excluded C2C scope executed the command')
    require(QQServerInterface.psi_opt() is None, 'Command/event context leaked into caller')
    runtime.permission_manager.set_permission(group, 2)
    try:
        runtime.command_manager.execute_command('!!cap_solo not-an-integer', group)
    except RuntimeNotReadyError:
        pass
    require([row for row in _journal() if row[0] == 'command'] == [['command', 'cap_solo', 7, 'group']],
            'Invalid Integer argument executed the callback')

    bad_dependency = Path('plugins/cap_missing.py')
    bad_dependency.write_text("PLUGIN_METADATA = {'id':'cap_missing','version':'1.0.0','dependencies':{'absent_capability':'*'}}\n", encoding='utf8')
    result = manager.load_plugin(bad_dependency).result(timeout=_TIMEOUT)
    require(not result.get_if_success(PluginResultType.LOAD) and manager.get_plugin_from_id('cap_missing') is None,
            'Missing dependency was admitted into the live registry')
    bad_metadata = Path('plugins/cap_invalid.py')
    bad_metadata.write_text("PLUGIN_METADATA = {'id':'cap_invalid','version':'1.0.0','entrypoint':'outside_plugin'}\n", encoding='utf8')
    result = manager.load_plugin(bad_metadata).result(timeout=_TIMEOUT)
    require(not result.get_if_success(PluginResultType.LOAD), 'Invalid metadata was admitted')
    require(all(manager.get_plugin_from_id(identity) is record for identity, record in zip(identities, records)),
            'Failed isolated plugin load disturbed valid records')


def _executors_context(runtime):
    from botcraft.plugin.si.server_interface import QQServerInterface
    from mcdreforged.plugin.si.server_interface import ServerInterface
    manager = runtime.plugin_manager
    solo = manager.get_plugin_from_id('cap_solo')
    directory = manager.get_plugin_from_id('cap_directory')
    with manager.with_plugin_context(solo):
        require(QQServerInterface.psi().get_self_metadata().id == 'cap_solo', 'Outer sync plugin context missing')
        with manager.with_plugin_context(directory):
            require(QQServerInterface.psi().get_self_metadata().id == 'cap_directory', 'Nested sync plugin context missing')
        require(QQServerInterface.psi().get_self_metadata().id == 'cap_solo', 'Nested sync plugin context did not restore')
    require(QQServerInterface.psi_opt() is None, 'Sync plugin context leaked after exit')
    require(runtime.server_interface.schedule_task(lambda: QQServerInterface.psi_opt()).result(timeout=_TIMEOUT) is None,
            'Unbound scheduled sync task acquired a plugin context')
    require(solo.server_interface.schedule_task(lambda: QQServerInterface.psi_opt()).result(timeout=_TIMEOUT) is None,
            'Calling a bound plugin interface gave scheduled work an invented context')

    async def context_probe():
        require(runtime.async_task_executor.is_on_thread(), 'Coroutine executed outside actual async executor')
        with manager.with_plugin_context(solo):
            await asyncio.sleep(0)
            with manager.with_plugin_context(directory):
                await asyncio.sleep(0)
                require(QQServerInterface.psi().get_self_metadata().id == 'cap_directory', 'Async nested context missing')
            require(QQServerInterface.psi().get_self_metadata().id == 'cap_solo', 'Async context did not restore across await')
        require(QQServerInterface.psi_opt() is None, 'Async context leaked after scope')
        return 42
    require(runtime.server_interface.schedule_task(context_probe()).result(timeout=_TIMEOUT) == 42, 'Async task did not deliver its computed result')
    async def concurrent_contexts():
        entered = asyncio.Event()
        release = asyncio.Event()
        async def first():
            with manager.with_plugin_context(solo):
                entered.set()
                await release.wait()
                return QQServerInterface.psi().get_self_metadata().id
        async def second():
            await entered.wait()
            with manager.with_plugin_context(directory):
                release.set()
                await asyncio.sleep(0)
                return QQServerInterface.psi().get_self_metadata().id
        return await asyncio.gather(first(), second())
    require(runtime.server_interface.schedule_task(concurrent_contexts()).result(timeout=_TIMEOUT) == ['cap_solo', 'cap_directory'],
            'Concurrent coroutine plugin contexts contaminated each other')
    require(runtime.server_interface.schedule_task(lambda: (runtime.sync_task_executor.is_on_thread(), 6 * 7)).result(timeout=_TIMEOUT) == (True, 42),
            'Sync task did not execute on its dedicated executor')
    def failed_task():
        raise ValueError('capability-task-error')
    failure = runtime.server_interface.schedule_task(failed_task)
    rejects(ValueError, lambda: failure.result(timeout=_TIMEOUT), 'Sync executor swallowed a task exception')
    async def failed_coroutine():
        await asyncio.sleep(0)
        raise ValueError('capability-coroutine-error')
    failure = runtime.server_interface.schedule_task(failed_coroutine())
    rejects(ValueError, lambda: failure.result(timeout=_TIMEOUT), 'Async executor swallowed a coroutine exception')
    async def prohibited_language_scope():
        with runtime.translation_manager.language_context('en_us'):
            await asyncio.sleep(0)
            runtime.translation_manager.tr('cap_solo.format', 'crossed-await', allow_failure=False)
    failure = runtime.server_interface.schedule_task(prohibited_language_scope())
    rejects(RuntimeError, lambda: failure.result(timeout=_TIMEOUT), 'Thread-local translation scope silently crossed await')
    require(ServerInterface.get_instance() is None, 'BotCraft changed the native MCDR singleton')


def _reload_unload(runtime, paths):
    from mcdreforged.plugin.operation_result import PluginResultType
    from mcdreforged.utils.exception import IllegalStateError
    from botcraft.plugin.si.server_interface import QQServerInterface
    from botcraft.utils.exception import RuntimeNotReadyError
    manager = runtime.plugin_manager
    # Dependents first, so each later failure cannot be attributed to a provider
    # intentionally removed by an earlier probe.
    for identity in ['cap_packed', 'cap_directory', 'cap_solo']:
        record = manager.get_plugin_from_id(identity)
        old_module = record.entry_module_instance
        result = manager.reload_plugin(record).result(timeout=_TIMEOUT)
        require(result.get_if_success(PluginResultType.RELOAD), 'Healthy {} reload failed'.format(identity))
        current = manager.get_plugin_from_id(identity)
        require(current is not None and current.entry_module_instance is not old_module
                and current.entry_module_instance.generation == 2, 'Reload did not replace entrypoint with previous-module state')
        stale_interface = current.server_interface
        unloaded = manager.unload_plugin(current).result(timeout=_TIMEOUT)
        require(unloaded.get_if_success(PluginResultType.UNLOAD) and manager.get_plugin_from_id(identity) is None,
                'Explicit {} unload failed'.format(identity))
        require(all(item.plugin.get_id() != identity for item in manager.registry_storage.help_messages),
                'Explicit unload retained help metadata')
        rejects(IllegalStateError, lambda: stale_interface.register_help_message('!!unloaded', 'unloaded'),
                'Explicitly unloaded record admitted registration')
        loaded = manager.load_plugin(paths[identity]).result(timeout=_TIMEOUT)
        require(loaded.get_if_success(PluginResultType.LOAD), 'Plugin could not load again after explicit unload')
        current = manager.get_plugin_from_id(identity)
        require(current is not None and current.entry_module_instance.generation == 1,
                'Fresh load after unload retained a previous entrypoint')
        stale_interface = current.server_interface
        loaded_module_name = current.entry_module_instance.__name__
        source_file = paths[identity]
        if identity == 'cap_solo':
            source_file.write_text(_plugin_code(identity, solo=True) + "\nraise RuntimeError('intentional capability reload failure')\n", encoding='utf8')
        elif identity == 'cap_directory':
            (source_file / identity / '__init__.py').write_text("raise RuntimeError('intentional capability reload failure')\n", encoding='utf8')
        else:
            with ZipFile(source_file, 'r') as archive:
                metadata = archive.read('botcraft.plugin.json')
            with ZipFile(source_file, 'w') as archive:
                archive.writestr('botcraft.plugin.json', metadata)
                archive.writestr(identity + '/__init__.py', "raise RuntimeError('intentional capability reload failure')\n")
        result = manager.reload_plugin(current).result(timeout=_TIMEOUT)
        require(not result.get_if_success(PluginResultType.RELOAD) and manager.get_plugin_from_id(identity) is None,
                'Failed {} reload kept a live plugin'.format(identity))
        require(loaded_module_name not in sys.modules, 'Failed reload retained the entrypoint module')
        require(all(item.plugin.get_id() != identity for item in manager.registry_storage.help_messages),
                'Failed reload retained plugin help registrations')
        rejects(IllegalStateError, lambda: stale_interface.register_help_message('!!stale', 'stale'), 'Unloaded plugin interface admitted new registration')
        rejects((KeyError, ValueError), lambda: runtime.translate(identity + '.format', 'x', language='en_us', allow_failure=False),
                'Failed reload retained plugin translations')
    require(QQServerInterface.psi_opt() is None, 'Reload/unload context leaked')
    require(any(row == ['unload', 'cap_solo'] for row in _journal()), 'Unload lifecycle was not called')
    source, _, _ = _source(runtime)
    before = [row for row in _journal() if row[0] == 'command']
    try:
        runtime.command_manager.execute_command('!!cap_solo 11', source)
    except RuntimeNotReadyError:
        pass
    require([row for row in _journal() if row[0] == 'command'] == before, 'Unloaded command was still executable')


def run_probes():
    stage = 'temporary-resources'
    runtime = None
    original_cwd = Path.cwd()
    try:
        with TemporaryDirectory(prefix='botcraft-probe-runtime-') as directory:
            os.chdir(directory)
            try:
                paths = _prepare()
                stage = 'native-singleton-before'
                from mcdreforged.plugin.si.server_interface import ServerInterface
                require(ServerInterface.get_instance() is None, 'Probe process already has a native MCDR host')
                stage = 'runtime-initialize'
                from botcraft.runtime import Runtime
                from botcraft.runtime_args import RuntimeArgs
                runtime = Runtime(RuntimeArgs())
                runtime.initialize_local()
                stage = 'configuration-permission-preference-storage'
                _config_permissions(runtime)
                stage = 'text-keyboard-recursive-models-source-receipt'
                _text_models(runtime)
                stage = 'runtime-start-local-file-plugins'
                runtime.start_local()
                stage = 'registry-dependencies-metadata-command-scope'
                _plugin_registry_commands(runtime, paths)
                stage = 'immediate-deferred-translation-keyboards'
                _translations(runtime)
                stage = 'sync-async-executors-plugin-context'
                _executors_context(runtime)
                stage = 'three-formats-reload-failure-unload'
                _reload_unload(runtime, paths)
            finally:
                active_error = sys.exc_info()[0] is not None
                try:
                    if runtime is not None:
                        if not active_error:
                            stage = 'runtime-cleanup'
                        runtime.stop()
                        if not active_error:
                            require(not runtime.sync_task_executor.get_thread().is_alive()
                                    and not runtime.async_task_executor.get_thread().is_alive(), 'Probe executors survived runtime.stop()')
                            from botcraft.plugin.si.server_interface import QQServerInterface
                            from mcdreforged.plugin.si.server_interface import ServerInterface
                            require(QQServerInterface.get_instance() is None, 'BotCraft global interface survived stop')
                            require(ServerInterface.get_instance() is None, 'Native MCDR singleton changed during cleanup')
                            require(not runtime.plugin_manager.get_regular_plugins(), 'Regular probe plugins survived stop')
                            require(all(not item.plugin.get_id().startswith('cap_') for item in runtime.plugin_manager.registry_storage.help_messages),
                                    'Probe registry entries survived stop')
                            require(not any(name.startswith(('cap_solo', 'cap_directory', 'cap_packed', 'BOTCRAFT_SOLO_PLUGIN@')) for name in sys.modules),
                                    'Probe-owned modules survived stop')
                finally:
                    os.chdir(original_cwd)
        return {'ok': True, 'stage': 'cleaned', 'coverage': 'local-runtime-only'}
    except BaseException as error:
        return {'ok': False, 'stage': stage, 'error': '{}: {}'.format(type(error).__name__, error),
                'traceback': traceback.format_exc()}
    finally:
        os.chdir(original_cwd)


def main():
    report = run_probes()
    print(_REPORT_PREFIX + json.dumps(report, ensure_ascii=True), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
