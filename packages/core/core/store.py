from __future__ import annotations

from typing import Protocol


class ObjectStore(Protocol):
    def exists(self, key: str) -> bool: ...

    def read_bytes(self, key: str) -> bytes: ...

    def write_bytes(self, key: str, body: bytes, content_type: str) -> None: ...
