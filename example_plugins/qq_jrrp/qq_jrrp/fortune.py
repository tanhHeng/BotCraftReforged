"""Daily fortune adapted from UnknownBits/LazyAlienWS (GPL-3.0-only).

Source: https://github.com/UnknownBits/LazyAlienWS/blob/main/plugins/qq_jrrp.py
Modified 2026-10-01 for NoneBot and non-numeric QQ OpenIDs.
Modified 2026-10-05: BotCraft port; fortune wording moved to translations.
"""

import hashlib
import random
from datetime import date


def day_seed(today: date) -> int:
    return int(today.strftime('%y%m%d'))


def daily_luck(user_id: str, today: date) -> int:
    # Keep numeric IDs compatible with the original seed; hash opaque OpenIDs.
    if user_id.isascii() and user_id.isdecimal():
        user_seed = int(user_id)
    else:
        user_seed = int.from_bytes(hashlib.sha256(user_id.encode('utf-8')).digest(), 'big')
    return random.Random(day_seed(today) + user_seed).randint(0, 100)


def luck_category(number: int) -> str:
    for threshold, category in (
        (16, 'great_luck'), (33, 'luck'), (50, 'small_luck'),
        (66, 'small_misfortune'), (83, 'misfortune'), (101, 'great_misfortune'),
    ):
        if number < threshold:
            return category
    raise ValueError('Luck number must be between 0 and 100')
