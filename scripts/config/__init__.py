"""配置层：数据模型、域名匹配、配置加载。"""

from .domain_pattern import DomainPattern
from .loader import load_config, strip_jsonc
from .models import (
    AppConfig,
    DnsConfig,
    DomainConfig,
    ProxyConfig,
    ResponseConfig,
    SniPattern,
    SpeedTestConfig,
    UpstreamConfig,
)

__all__ = [
    "DomainPattern",
    "load_config",
    "strip_jsonc",
    "AppConfig",
    "DnsConfig",
    "DomainConfig",
    "ProxyConfig",
    "ResponseConfig",
    "SniPattern",
    "SpeedTestConfig",
    "UpstreamConfig",
]