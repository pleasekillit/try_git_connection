"""IP 服务：并发 TCP 连接测速并排序。"""
from __future__ import annotations

import logging
import math
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Sequence, Tuple

from ..config import SpeedTestConfig
from .dns_client import DnsClient

logger = logging.getLogger(__name__)


class IpAddressService:
    """对候选 IP 做连接测速，返回最快的若干 IP。"""

    def __init__(self, dns: DnsClient, speed: SpeedTestConfig) -> None:
        self._dns = dns
        self._speed = speed
        self._elapsed_cache: Dict[Tuple[str, int], Tuple[float, float]] = {}

    def get_addresses(self, host: str, port: int, extra_ips: Sequence[str] = ()) -> List[str]:
        """返回按连接时延升序排列的 IP（最多 max_ip_count 个）。

        ``extra_ips`` 为配置中的备用候选 IP，与 DNS 结果合并后一起测速，
        以便在 DNS 只返回不可用 IP 时仍能选到可达地址。
        """
        addresses = list(dict.fromkeys(self._dns.resolve(host) + list(extra_ips)))
        if not addresses:
            return []

        with ThreadPoolExecutor(max_workers=len(addresses)) as executor:
            elapsed_list = list(executor.map(lambda ip: self._test(ip, port), addresses))

        ranked = sorted(zip(addresses, elapsed_list), key=lambda item: item[1])
        reachable = [ip for ip, elapsed in ranked if not math.isinf(elapsed)]
        return reachable[: self._speed.max_ip_count]

    def _test(self, ip: str, port: int) -> float:
        """测量连接指定 IP:PORT 的耗时；失败返回 inf。"""
        key = (ip, port)
        now = time.monotonic()
        cached = self._elapsed_cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

        start = time.perf_counter()
        try:
            with socket.create_connection((ip, port), timeout=self._speed.connect_timeout):
                elapsed = time.perf_counter() - start
        except OSError:
            elapsed = math.inf

        self._elapsed_cache[key] = (now + self._speed.cache_ttl, elapsed)
        return elapsed