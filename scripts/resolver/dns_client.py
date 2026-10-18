"""DNS 客户端：DoH 优先、TCP DNS 兜底，绕过本地 DNS 污染。"""
from __future__ import annotations

import ipaddress
import logging
import time
from typing import Callable, Dict, List, Tuple

import dns.message
import dns.query
import dns.rdatatype

from ..config import DnsConfig

logger = logging.getLogger(__name__)


class DnsClient:
    """纯净 DNS 解析器，带结果缓存。"""

    def __init__(self, config: DnsConfig) -> None:
        self._config = config
        self._cache: Dict[str, Tuple[float, List[str]]] = {}

    def resolve(self, host: str) -> List[str]:
        """解析域名，返回去重且已过滤回环地址的 IP 列表。"""
        now = time.monotonic()
        cached = self._cache.get(host)
        if cached is not None and cached[0] > now:
            return cached[1]

        addresses = self._resolve_uncached(host)
        self._cache[host] = (now + self._config.dns_cache_ttl, addresses)
        return addresses

    def _resolve_uncached(self, host: str) -> List[str]:
        result: List[str] = []
        seen = set()

        def collect(items: List[str]) -> None:
            for ip in items:
                if ip not in seen:
                    seen.add(ip)
                    result.append(ip)

        for url in self._config.doh_servers:
            collect(self._query(host, lambda q, u=url: dns.query.https(q, u, timeout=self._config.resolve_timeout)))

        if not result:
            for server in self._config.tcp_servers:
                collect(self._query(host, lambda q, s=server: self._query_tcp(s, q)))

        return [ip for ip in result if not ipaddress.ip_address(ip).is_loopback]

    def _query_tcp(self, server: str, question) -> "dns.message.Message":
        host, _, port = server.partition(":")
        return dns.query.tcp(
            question, host, port=int(port or 53), timeout=self._config.resolve_timeout
        )

    def _query(self, host: str, query_fn: Callable[[object], object]) -> List[str]:
        addresses: List[str] = []
        for rdtype in (dns.rdatatype.A, dns.rdatatype.AAAA):
            question = dns.message.make_query(host, rdtype)
            try:
                response = query_fn(question)
            except Exception as ex:  # noqa: BLE001 - 单个 DNS 服务器失败不影响其它
                logger.debug("DNS 查询 %s (%s) 失败: %s", host, rdtype, ex)
                continue
            for rrset in response.answer:
                if rrset.rdtype in (dns.rdatatype.A, dns.rdatatype.AAAA):
                    for rdata in rrset:
                        addresses.append(rdata.address)
        return addresses