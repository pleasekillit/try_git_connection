"""配置数据模型与 SNI 表达式。"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .domain_pattern import DomainPattern


@dataclass(frozen=True)
class ResponseConfig:
    """命中域名后直接返回的自定义响应。"""

    status_code: int = 200
    content_type: str = "text/plain;charset=utf-8"
    content_value: Optional[str] = None


class SniPattern:
    """SNI 表达式：支持 @domain / @ipaddress / @random 变量。"""

    NONE = ""
    DOMAIN = "@domain"
    IPADDRESS = "@ipaddress"
    RANDOM = "@random"

    __slots__ = ("value",)

    def __init__(self, value: str = "") -> None:
        self.value = value or ""

    def with_domain(self, domain: str) -> "SniPattern":
        return SniPattern(self.value.replace(self.DOMAIN, domain))

    def with_ip(self, ip: str) -> "SniPattern":
        return SniPattern(self.value.replace(self.IPADDRESS, ip))

    def with_random(self) -> "SniPattern":
        return SniPattern(self.value.replace(self.RANDOM, str(random.getrandbits(32))))

    @property
    def enabled(self) -> bool:
        """是否发送 SNI（空值表示不发送）。"""
        return self.value != ""

    def __repr__(self) -> str:
        return f"SniPattern({self.value!r})"


@dataclass(frozen=True)
class DomainConfig:
    """单个域名的代理策略。"""

    tls_sni: bool = True
    tls_sni_pattern: Optional[str] = None
    tls_ignore_name_mismatch: bool = False
    timeout: Optional[float] = None
    ip_address: Optional[str] = None
    #: 备用候选 IP：当 DNS 只返回单个不稳定 IP（如 GitHub 的 20.205.243.x）时兜底
    ip_addresses: List[str] = field(default_factory=list)
    destination: Optional[str] = None
    response: Optional[ResponseConfig] = None

    def sni_pattern(self) -> SniPattern:
        """根据配置推导 SNI 表达式。"""
        if not self.tls_sni:
            return SniPattern(SniPattern.NONE)
        if not self.tls_sni_pattern:
            return SniPattern(SniPattern.DOMAIN)
        return SniPattern(self.tls_sni_pattern)


@dataclass
class ProxyConfig:
    listen: str = "127.0.0.1"
    port: int = 38457


@dataclass
class DnsConfig:
    doh_servers: List[str] = field(default_factory=list)
    tcp_servers: List[str] = field(default_factory=list)
    resolve_timeout: float = 4.0
    dns_cache_ttl: float = 300.0


@dataclass
class SpeedTestConfig:
    connect_timeout: float = 2.0
    max_ip_count: int = 3
    cache_ttl: float = 300.0


@dataclass
class UpstreamConfig:
    connect_timeout: float = 10.0


@dataclass
class AppConfig:
    """应用总配置。``domains`` 已按优先级排序。"""

    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    dns: DnsConfig = field(default_factory=DnsConfig)
    speed_test: SpeedTestConfig = field(default_factory=SpeedTestConfig)
    upstream: UpstreamConfig = field(default_factory=UpstreamConfig)
    domains: List[Tuple[DomainPattern, DomainConfig]] = field(default_factory=list)

    def match(self, domain: str) -> Optional[DomainConfig]:
        """返回首个匹配的域名规则；无匹配返回 None。"""
        for pattern, config in self.domains:
            if pattern.is_match(domain):
                return config
        return None

    def match_pattern(self, domain: str) -> Optional[DomainPattern]:
        for pattern, _ in self.domains:
            if pattern.is_match(domain):
                return pattern
        return None