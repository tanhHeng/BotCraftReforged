"""Synchronous validation/snapshot boundary for typed QQ operations."""
import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import heapq
import math
from threading import RLock, Timer
import time

from botcraft.event.qq_event import QQEvent
from botcraft.event.qq_interaction import QQInteraction
from botcraft.message.message_received import QQMessageReceived
from botcraft.message.message_receipt import QQMessageReceipt
from botcraft.message.user import Group, User
from botcraft.message.qtext.text import QTextBase, QText, QMarkdown
from botcraft.network.exception import NetworkError, NotReadyError, ResultUnknownError
from botcraft.utils.exception import PassiveReplyExpiredError


@dataclass
class _Passive:
    first_seen: float
    expires_at: float
    sequence: int = 0


class MessageSender:
    PASSIVE_RETENTION = 600

    def __init__(self, runtime):
        self.runtime = runtime
        self._lock = RLock()
        self._passive = {}
        self._expirations = []
        self._interactions = set()
        self._expiry_timer = None
        self._timer_generation = 0
        self._closed = False

    def _arm_expiry(self):
        if not self._closed and self._expiry_timer is None and self._expirations:
            delay = max(0, self._expirations[0][0] - time.monotonic())
            self._timer_generation += 1
            self._expiry_timer = Timer(delay, self._expire_passive, args=(self._timer_generation,))
            self._expiry_timer.daemon = True
            self._expiry_timer.start()

    def _expire_passive(self, generation):
        with self._lock:
            if generation != self._timer_generation:
                return
            self._expiry_timer = None
            self._cleanup(time.monotonic())
            self._arm_expiry()

    def close(self):
        with self._lock:
            self._closed = True
            self._timer_generation += 1
            if self._expiry_timer is not None:
                self._expiry_timer.cancel()
                self._expiry_timer = None
            self._passive.clear()
            self._expirations.clear()

    @staticmethod
    def _string(value, name):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'{name} must be a non-empty string')
        return value

    @staticmethod
    def _route(target):
        if not isinstance(target, (User, Group)):
            raise TypeError('target must be User or Group')
        scene, conversation = target.route()
        scene = getattr(scene, 'value', scene)
        if scene not in ('group', 'c2c'):
            raise ValueError('Only group and c2c are supported')
        return scene, MessageSender._string(conversation, 'conversation')

    @staticmethod
    def _incoming_route(event):
        payload = event.raw_payload
        data = payload.get('d')
        if not isinstance(data, dict):
            raise ValueError('event has no object data')
        if payload.get('t') in ('GROUP_MESSAGE_CREATE', 'GROUP_AT_MESSAGE_CREATE', 'GROUP_ADD_ROBOT', 'GROUP_MSG_RECEIVE'):
            return 'group', MessageSender._string(data.get('group_openid'), 'group_openid')
        if payload.get('t') == 'C2C_MESSAGE_CREATE':
            author = data.get('author')
            if not isinstance(author, dict):
                raise ValueError('message has no author')
            return 'c2c', MessageSender._string(author.get('user_openid'), 'user_openid')
        raise ValueError('event does not have a supported message route')

    def _ready(self):
        if self.runtime.is_stopping() or not self.runtime.is_ready() or not self.runtime.gateway.is_ready():
            raise NotReadyError('QQ runtime/gateway is not ready for new operations')

    def _cleanup(self, now):
        while self._expirations and self._expirations[0][0] <= now:
            expiry, key = heapq.heappop(self._expirations)
            entry = self._passive.get(key)
            if entry is not None and entry.expires_at == expiry:
                del self._passive[key]

    @staticmethod
    def _platform_time(event):
        timestamp = event.raw_payload.get('d', {}).get('timestamp')
        relationship = event.raw_payload.get('t') in ('GROUP_ADD_ROBOT', 'GROUP_MSG_RECEIVE')
        try:
            if relationship:
                if isinstance(timestamp, bool) or not isinstance(timestamp, int):
                    raise ValueError
                value = float(timestamp)
            else:
                if not isinstance(timestamp, str):
                    raise ValueError
                parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise ValueError
                value = parsed.timestamp()
            if not math.isfinite(value) or value <= 0 or value > time.time() + 5:
                raise ValueError
            return value
        except (ValueError, TypeError, OverflowError, OSError):
            raise ValueError('passive context lacks a trustworthy original platform timestamp') from None

    def register_incoming(self, event):
        if not isinstance(event, QQEvent):
            raise TypeError('incoming must be QQEvent')
        if self._closed:
            return
        kind = event.raw_payload.get('t')
        if kind not in ('GROUP_MESSAGE_CREATE', 'GROUP_AT_MESSAGE_CREATE', 'C2C_MESSAGE_CREATE',
                        'GROUP_ADD_ROBOT', 'GROUP_MSG_RECEIVE'):
            return
        try:
            scene, conversation = self._incoming_route(event)
            association = event.raw_payload.get('id') if kind in ('GROUP_ADD_ROBOT', 'GROUP_MSG_RECEIVE') else event.raw_payload['d'].get('id')
            association = self._string(association, 'passive association id')
        except (ValueError, KeyError):
            return  # Parsing/command-source validation reports malformed incoming facts.
        field = 'event_id' if kind in ('GROUP_ADD_ROBOT', 'GROUP_MSG_RECEIVE') else 'msg_id'
        key = (scene, conversation, field, association)
        now = time.monotonic()
        try:
            platform_time = self._platform_time(event)
        except ValueError:
            event._passive_deadline = float('-inf')
            return
        deadline = min(getattr(event, 'received_at', now) + self.PASSIVE_RETENTION,
                       now + platform_time + self.PASSIVE_RETENTION - time.time())
        with self._lock:
            self._cleanup(now)
            if deadline <= now:
                event._passive_deadline = deadline
                return
            if key not in self._passive:
                first = getattr(event, 'received_at', now)
                entry = _Passive(first, deadline)
                self._passive[key] = entry
                heapq.heappush(self._expirations, (entry.expires_at, key))
                self._arm_expiry()
            entry = self._passive[key]
            event._passive_deadline = entry.expires_at

    def _passive_seq(self, scene, conversation, field, association, context):
        if not isinstance(context, QQEvent):
            raise ValueError('passive sending requires the original incoming event')
        expected_route = self._incoming_route(context)
        if expected_route != (scene, conversation):
            raise ValueError('passive context belongs to a different conversation')
        expected = context.raw_payload.get('id') if field == 'event_id' else context.raw_payload['d'].get('id')
        if expected != association:
            raise ValueError('passive id does not match the original incoming event')
        self._platform_time(context)
        key = (scene, conversation, field, association)
        now = time.monotonic()
        with self._lock:
            self._cleanup(now)
            entry = self._passive.get(key)
            if entry is None or now >= entry.expires_at or now >= getattr(context, '_passive_deadline', float('-inf')):
                raise PassiveReplyExpiredError('passive association is expired or was not registered on receipt')
            entry.sequence += 1
            return entry.sequence

    def _reference(self, message, scene, conversation):
        if message is None:
            return None
        if isinstance(message, QQMessageReceived):
            route = self._incoming_route(message)
            data = message.raw_payload.get('d', {})
            ext = data.get('message_scene', {}).get('ext') if isinstance(data.get('message_scene'), dict) else None
            index = None
            if isinstance(ext, list):
                for item in ext:
                    if isinstance(item, str) and item.startswith('msg_idx='):
                        index = item.partition('=')[2]
                        break
        elif isinstance(message, QQMessageReceipt):
            route = (getattr(message.scene, 'value', message.scene), message.conversation)
            ext = message.raw_response.get('ext_info')
            index = ext.get('ref_idx') if isinstance(ext, dict) else None
        else:
            raise TypeError('refer_msg must be QQMessageReceived, QQMessageReceipt or None')
        if route != (scene, conversation):
            raise ValueError('reference belongs to a different conversation')
        return {'message_id': self._string(index, 'reference index')}

    def _content(self, message, target, mention):
        if not isinstance(message, (str, QTextBase)):
            raise TypeError('message must be str or QTextBase')
        evaluated = self.runtime.translation_manager.evaluate(message)
        text = QText(evaluated) if isinstance(evaluated, str) else evaluated
        if not isinstance(text, QTextBase):
            raise TypeError('evaluated message must be str or QTextBase')
        payload = deepcopy(text.to_payload())
        if not isinstance(payload, dict):
            raise TypeError('message encoder must return a dict')
        if mention:
            if not isinstance(target, User):
                raise TypeError('mention target must be User')
            scene, _ = self._route(target)
            if scene == 'group':
                identity = self._string(target.member_openid, 'member_openid for mention')
                if any(char in identity for char in '<>\r\n"&'):
                    raise ValueError('invalid mention identity')
                if isinstance(text, QText):
                    payload['content'] = f'<qqbot-at-user id="{identity}" /> ' + self._string(payload.get('content'), 'content')
                elif isinstance(text, QMarkdown):
                    markdown = payload.get('markdown')
                    if not isinstance(markdown, dict):
                        raise ValueError('invalid Markdown payload')
                    markdown['content'] = f'<qqbot-at-user id="{identity}" /> ' + self._string(markdown.get('content'), 'markdown content')
                else:
                    raise TypeError('this content does not support a group mention')
        return payload

    def send(self, target, message, *, refer_msg=None, msg_id=None, event_id=None,
             passive_context=None, mention=False):
        scene, conversation = self._route(target)
        if not isinstance(mention, bool):
            raise TypeError('mention must be bool')
        if msg_id is not None and event_id is not None:
            raise ValueError('msg_id and event_id are mutually exclusive')
        if msg_id is not None:
            self._string(msg_id, 'msg_id')
        if event_id is not None:
            self._string(event_id, 'event_id')
            if not isinstance(passive_context, QQEvent) or passive_context.raw_payload.get('t') not in ('GROUP_ADD_ROBOT', 'GROUP_MSG_RECEIVE'):
                raise ValueError('event passive sending only supports GROUP_ADD_ROBOT/GROUP_MSG_RECEIVE')
        if passive_context is not None and msg_id is None and event_id is None:
            raise ValueError('passive context requires msg_id or event_id')
        payload = self._content(message, target, mention)
        reference = self._reference(refer_msg, scene, conversation)
        if reference is not None:
            payload['message_reference'] = reference
        self._ready()
        if msg_id is not None or event_id is not None:
            field, association = ('msg_id', msg_id) if msg_id is not None else ('event_id', event_id)
            sequence = self._passive_seq(scene, conversation, field, association, passive_context)
            payload[field] = association
            if msg_id is not None:
                payload['msg_seq'] = sequence

        async def send_snapshot():
            raw = await self.runtime.api_client.send_message(scene, conversation, payload)
            return QQMessageReceipt(raw, scene, conversation)

        return self.runtime.network_loop.submit(send_snapshot(), operation=f'send {scene} message')

    def reply(self, source, message, *, refer_msg=None):
        from botcraft.command.command_source import QQCommandSource
        if not isinstance(source, QQCommandSource):
            raise TypeError('reply requires QQCommandSource')
        msg_id = self._string(source.msg_id, 'source msg_id')
        origin = source.origin_received
        if not isinstance(origin, QQMessageReceived):
            raise ValueError('source has no original incoming message')
        return self.send(origin.original_user, message, refer_msg=refer_msg, msg_id=msg_id, passive_context=origin)

    def reply_event(self, event, message, *, refer_msg=None):
        if not isinstance(event, QQEvent) or event.raw_payload.get('t') not in ('GROUP_ADD_ROBOT', 'GROUP_MSG_RECEIVE'):
            raise TypeError('reply_event requires GROUP_ADD_ROBOT or GROUP_MSG_RECEIVE QQEvent')
        scene, conversation = self._incoming_route(event)
        event_id = self._string(event.raw_payload.get('id'), 'event_id')
        return self.send(Group(group_openid=conversation), message, refer_msg=refer_msg,
                         event_id=event_id, passive_context=event)

    def delete_message(self, message):
        if isinstance(message, QQMessageReceived):
            scene, conversation = self._incoming_route(message)
            id = self._string(message.raw_payload['d'].get('id'), 'message id')
        elif isinstance(message, QQMessageReceipt):
            scene, conversation = getattr(message.scene, 'value', message.scene), message.conversation
            id = self._string(message.raw_response.get('id'), 'message id')
        else:
            raise TypeError('delete_message requires QQMessageReceived or QQMessageReceipt')
        self._string(conversation, 'conversation')
        if scene not in ('group', 'c2c'):
            raise ValueError('Only group and c2c are supported')
        self._ready()
        return self.runtime.network_loop.submit(self.runtime.api_client.delete_message(scene, conversation, id),
                                                operation=f'delete {scene} message')

    def delete_message_with_id(self, target, id):
        scene, conversation = self._route(target)
        id = self._string(id, 'message id')
        self._ready()
        return self.runtime.network_loop.submit(self.runtime.api_client.delete_message(scene, conversation, id),
                                                operation=f'delete {scene} message')

    def respond_interaction(self, event, code):
        if not isinstance(event, QQInteraction):
            raise TypeError('respond_interaction requires QQInteraction')
        value = code.value if isinstance(code, Enum) else code
        if isinstance(value, bool) or not isinstance(value, int) or value not in range(6):
            raise ValueError('interaction response code must be an integer from 0 through 5')
        data = event.raw_payload.get('d')
        id = self._string(data.get('id') if isinstance(data, dict) else None, 'interaction id')
        self._ready()
        with self._lock:
            if id in self._interactions:
                raise ValueError('this interaction response is already submitted')
            self._interactions.add(id)

        async def respond_snapshot():
            try:
                await self.runtime.api_client.respond_interaction(id, value)
            except asyncio.CancelledError:
                # ApiClient converts cancellation after transmission to UNKNOWN;
                # plain cancellation here is therefore definitely pre-transmission.
                with self._lock:
                    self._interactions.discard(id)
                raise
            except NetworkError as error:
                if not isinstance(error, ResultUnknownError):
                    with self._lock:
                        self._interactions.discard(id)
                raise

        try:
            return self.runtime.network_loop.submit(respond_snapshot(), operation='respond interaction')
        except BaseException:
            with self._lock:
                self._interactions.discard(id)
            raise
