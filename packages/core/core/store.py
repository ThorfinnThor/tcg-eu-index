from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ObjectStat:
    key: str
    size: int
    etag: str | None


class ObjectStore(Protocol):
    def exists(self, key: str) -> bool: ...

    def read_bytes(self, key: str) -> bytes: ...

    def write_bytes(self, key: str, body: bytes, content_type: str) -> None: ...

    def list_keys(self, prefix: str) -> list[str]: ...

    def list_objects(self, prefix: str) -> list[ObjectStat]: ...
