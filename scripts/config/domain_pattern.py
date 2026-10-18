"""域名表达式匹配。

规则与原版 FastGithub 一致：``*`` 表示除 ``.`` 之外的 0 到多个字符。
"""
from __future__ import annotations

import re
from functools import total_ordering

# 排序时 '*' 的占位符：保证其排在任意普通字符之后（对应 C# 的 char.MaxValue）
_WILDCARD = "\uffff"


@total_ordering
class DomainPattern:
    """域名表达式，支持 ``*`` 通配符。"""

    __slots__ = ("pattern", "_regex", "_sort_key")

    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        regex_pattern = re.escape(pattern).replace(r"\*", r"[^\.]*")
        self._regex = re.compile(f"^{regex_pattern}$", re.IGNORECASE)
        self._sort_key = self._build_sort_key(pattern)

    @staticmethod
    def _build_sort_key(pattern: str):
        """构造排序键：段数升序，段相同则自右向左比较，'*' 靠后。"""
        segments = pattern.split(".")
        normalized = tuple(seg.replace("*", _WILDCARD) for seg in reversed(segments))
        return (len(segments), normalized)

    def is_match(self, domain: str) -> bool:
        """域名是否匹配本表达式。"""
        return self._regex.match(domain) is not None

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, DomainPattern):
            return NotImplemented
        return self._sort_key < other._sort_key

    def __eq__(self, other: object) -> bool:
        return isinstance(other, DomainPattern) and self.pattern.lower() == other.pattern.lower()

    def __hash__(self) -> int:
        return hash(self.pattern.lower())

    def __repr__(self) -> str:
        return f"DomainPattern({self.pattern!r})"