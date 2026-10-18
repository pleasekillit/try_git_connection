"""上下行流量统计。"""
from __future__ import annotations

import threading
from typing import Dict


class FlowAnalyzer:
    """线程安全的流量计数器。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._up = 0
        self._down = 0

    def add_up(self, size: int) -> None:
        if size <= 0:
            return
        with self._lock:
            self._up += size

    def add_down(self, size: int) -> None:
        if size <= 0:
            return
        with self._lock:
            self._down += size

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return {"up": self._up, "down": self._down}