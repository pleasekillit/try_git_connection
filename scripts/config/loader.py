"""配置加载：JSONC 解析、多文件合并、模型装配。

配置文件与代码分离，全部位于 ``data/`` 目录：
- ``data/appsettings.json``：全局参数
- ``data/appsettings/appsettings.*.json``：按分组拆分的域名规则
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .domain_pattern import DomainPattern
from .models import (
    AppConfig,
    DnsConfig,
    DomainConfig,
    ProxyConfig,
    ResponseConfig,
    SpeedTestConfig,
    UpstreamConfig,
)


def strip_jsonc(text: str) -> str:
    """去掉 JSON 中的 ``//`` 与 ``/* */`` 注释（字符串内的内容保持不变）。"""
    result: List[str] = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            result.append(ch)
            if ch == "\\" and i + 1 < n:
                result.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        result.append(ch)
        i += 1
    return "".join(result)


def _loads_jsonc(text: str) -> Dict[str, Any]:
    return json.loads(strip_jsonc(text))


def _pick(data: Dict[str, Any], *names: str, default: Any = None) -> Any:
    """兼容 snake_case 与 PascalCase 两种键名。"""
    for name in names:
        if name in data:
            return data[name]
    return default


def _to_response_config(data: Optional[Dict[str, Any]]) -> Optional[ResponseConfig]:
    if not data:
        return None
    return ResponseConfig(
        status_code=int(_pick(data, "status_code", "StatusCode", default=200)),
        content_type=_pick(data, "content_type", "ContentType", default="text/plain;charset=utf-8"),
        content_value=_pick(data, "content_value", "ContentValue", default=None),
    )


def _to_domain_config(data: Optional[Dict[str, Any]]) -> DomainConfig:
    data = data or {}
    timeout = _pick(data, "timeout", "Timeout", default=None)
    return DomainConfig(
        tls_sni=bool(_pick(data, "tls_sni", "TlsSni", default=True)),
        tls_sni_pattern=_pick(data, "tls_sni_pattern", "TlsSniPattern", default=None),
        tls_ignore_name_mismatch=bool(
            _pick(data, "tls_ignore_name_mismatch", "TlsIgnoreNameMismatch", default=False)
        ),
        timeout=float(timeout) if timeout is not None else None,
        ip_address=_pick(data, "ip_address", "IPAddress", default=None),
        ip_addresses=list(_pick(data, "ip_addresses", "IPAddresses", default=[]) or []),
        destination=_pick(data, "destination", "Destination", default=None),
        response=_to_response_config(_pick(data, "response", "Response", default=None)),
    )


def load_config(data_dir: str | Path) -> AppConfig:
    """从数据目录装配 ``AppConfig``。"""
    data_dir = Path(data_dir)
    main_file = data_dir / "appsettings.json"
    if not main_file.is_file():
        raise FileNotFoundError(f"未找到主配置文件: {main_file}")

    raw = _loads_jsonc(main_file.read_text(encoding="utf-8"))

    # 合并按分组拆分的域名规则（文件名排序，后者覆盖前者）
    domains_raw: Dict[str, Any] = dict(raw.get("domains", {}))
    group_dir = data_dir / "appsettings"
    if group_dir.is_dir():
        for file in sorted(group_dir.glob("appsettings.*.json")):
            group_raw = _loads_jsonc(file.read_text(encoding="utf-8"))
            domains_raw.update(group_raw.get("domains", {}))

    proxy = ProxyConfig(
        listen=_pick(raw.get("proxy", {}), "listen", "Listen", default="127.0.0.1"),
        port=int(_pick(raw.get("proxy", {}), "port", "Port", default=38457)),
    )
    dns_raw = raw.get("dns", {})
    dns = DnsConfig(
        doh_servers=list(_pick(dns_raw, "doh_servers", "DohServers", default=[])),
        tcp_servers=list(_pick(dns_raw, "tcp_servers", "TcpServers", default=[])),
        resolve_timeout=float(_pick(dns_raw, "resolve_timeout", "ResolveTimeout", default=4.0)),
        dns_cache_ttl=float(_pick(dns_raw, "dns_cache_ttl", "DnsCacheTtl", default=300.0)),
    )
    speed_raw = raw.get("speed_test", {})
    speed = SpeedTestConfig(
        connect_timeout=float(_pick(speed_raw, "connect_timeout", "ConnectTimeout", default=2.0)),
        max_ip_count=int(_pick(speed_raw, "max_ip_count", "MaxIpCount", default=3)),
        cache_ttl=float(_pick(speed_raw, "cache_ttl", "CacheTtl", default=300.0)),
    )
    upstream = UpstreamConfig(
        connect_timeout=float(
            _pick(raw.get("upstream", {}), "connect_timeout", "ConnectTimeout", default=10.0)
        )
    )

    domains: List = []
    for pattern_str, cfg in domains_raw.items():
        domains.append((DomainPattern(pattern_str), _to_domain_config(cfg)))
    domains.sort(key=lambda item: item[0])

    return AppConfig(proxy=proxy, dns=dns, speed_test=speed, upstream=upstream, domains=domains)