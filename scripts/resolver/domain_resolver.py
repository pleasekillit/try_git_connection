"""域名解析器：为上游连接提供"域名 -> 有序 IP"的结果，带 TTL 缓存。"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Sequence, Tuple

from .ip_service import IpAddressService

logger = logging.getLogger(__name__)


class DomainResolver:
    """组合 DNS 解析与测速，并缓存结果。"""

    def __init__(self, ip_service: IpAddressService, ttl: float) -> None:
        self._ip_service = ip_service
        self._ttl = ttl
        self._cache: Dict[Tuple[str, int, Tuple[str, ...]], Tuple[float, List[str]]] = {}

    def resolve(self, host: str, port: int = 443, extra_ips: Sequence[str] = ()) -> List[str]:
        key = (host, port, tuple(extra_ips))
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

        addresses = self._ip_service.get_addresses(host, port, extra_ips)
        if addresses:
            logger.info("%s:%s -> %s", host, port, addresses)
        self._cache[key] = (now + self._ttl, addresses)
        return addresses

    def clear(self) -> None:
        self._cache.clear()