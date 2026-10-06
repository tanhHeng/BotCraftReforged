"""JSON quote storage adapted from LazyAlienWS (GPL-3.0-only).

Modified 2026-10-01: typed records, atomic writes and owner-only withdrawal.
Modified 2026-10-05: stdlib validation and synchronous BotCraft command I/O.
"""

import json
import os
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from typing_extensions import Self

from .fortune import day_seed


@dataclass(frozen=True)
class Sentence:
    sender: str | int
    sentence: str
    source: str

    def __post_init__(self: Self) -> None:
        if type(self.sender) not in (str, int):
            raise ValueError('Sentence sender must be a string or integer')
        if not isinstance(self.sentence, str) or not self.sentence:
            raise ValueError('Sentence text must be a non-empty string')
        if not isinstance(self.source, str) or not self.source:
            raise ValueError('Sentence source must be a non-empty string')

    @classmethod
    def from_record(cls: type[Self], record: object) -> Self:
        if not isinstance(record, dict) or not {'sender', 'sentence', 'from'} <= record.keys():
            raise ValueError('Sentence record requires sender, sentence and from fields')
        return cls(record['sender'], record['sentence'], record['from'])

    def to_record(self: Self) -> dict[str, str | int]:
        return {'sender': self.sender, 'sentence': self.sentence, 'from': self.source}


class SentenceStore:
    """Serialize local file access without scheduling background work."""

    def __init__(self: Self, path: Path) -> None:
        self.path = path
        self._lock = Lock()

    def _read(self: Self) -> list[Sentence]:
        try:
            content = self.path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return []
        records = json.loads(content)
        if not isinstance(records, list):
            raise ValueError('Sentence file must contain a JSON list')
        return [Sentence.from_record(record) for record in records]

    def _write(self: Self, sentences: list[Sentence]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=self.path.parent,
                prefix=f'.{self.path.name}.', suffix='.tmp', delete=False,
            ) as file:
                temporary = Path(file.name)
                json.dump([sentence.to_record() for sentence in sentences], file,
                          ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            temporary.replace(self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def choose(self: Self, luck_number: int, today: date) -> Sentence | None:
        with self._lock:
            sentences = self._read()
        if not sentences:
            return None
        # Preserve upstream's three daily seeds, including duplicate selections.
        variant = random.randint(0, min(2, len(sentences) - 1))
        generator = random.Random(day_seed(today) + luck_number + variant)
        return sentences[generator.randint(0, len(sentences) - 1)]

    def add(self: Self, sentence: Sentence) -> None:
        with self._lock:
            sentences = self._read()
            sentences.append(sentence)
            self._write(sentences)

    def withdraw(self: Self, sender: str) -> Sentence | None:
        with self._lock:
            sentences = self._read()
            for index in range(len(sentences) - 1, -1, -1):
                if sentences[index].sender == sender:
                    removed = sentences.pop(index)
                    self._write(sentences)
                    return removed
        return None
