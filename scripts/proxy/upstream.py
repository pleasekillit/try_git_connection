"""上游连接：选择最快 IP，并按域名策略定制 TLS/SNI。"""
from __future__ import annotations

import logging
import socket
import ssl
from typing import List, Tuple

from ..config import DomainConfig, UpstreamConfig
from ..resolver import DomainResolver
from .http_message import read_response

logger = logging.getLogger(__name__)


def build_client_ssl_context(cfg: DomainConfig) -> ssl.SSLContext:
    """构造访问上游的客户端 SSLContext。

    - 一律关闭主机名校验（SNI 可能被伪造或关闭）；
    - ``tls_ignore_name_mismatch`` 为真时不算验证证书链，否则仍验证链。
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE if cfg.tls_ignore_name_mismatch else ssl.CERT_REQUIRED
    return context


class Upstream:
    """建立到上下游目标服务器的连接并转发一次请求。"""

    def __init__(self, resolver: DomainResolver, config: UpstreamConfig) -> None:
        self._resolver = resolver
        self._config = config

    def _candidates(self, host: str, port: int, cfg: DomainConfig) -> List[str]:
        """汇总候选 IP：配置的固定/备用 IP 与 DNS 解析结果合并后统一测速排序。"""
        extra: List[str] = []
        if cfg.ip_address:
            extra.append(cfg.ip_address)
        extra.extend(cfg.ip_addresses)
        return self._resolver.resolve(host, port, extra)

    def connect(self, host: str, port: int, use_tls: bool, cfg: DomainConfig) -> socket.socket:
        """依次尝试候选 IP，返回已建立（必要时已 TLS 握手）的套接字。"""
        last_error: Exception | None = None
        for ip in self._candidates(host, port, cfg):
            try:
                sock = socket.create_connection((ip, port), timeout=self._config.connect_timeout)
            except OSError as ex:
                last_error = ex
                continue

            if not use_tls:
                return sock

            try:
                return self._wrap_tls(sock, host, ip, cfg)
            except (ssl.SSLError, OSError) as ex:
                last_error = ex
                sock.close()
                continue

        raise ConnectionError(f"无法连接到 {host}:{port} ({last_error})")

    def _wrap_tls(self, sock: socket.socket, host: str, ip: str, cfg: DomainConfig) -> socket.socket:
        sni = cfg.sni_pattern().with_domain(host).with_ip(ip).with_random()
        server_hostname = sni.value if sni.enabled else None
        context = build_client_ssl_context(cfg)
        wrapped = context.wrap_socket(sock, server_hostname=server_hostname)
        logger.debug("上游 TLS: %s -> %s (SNI=%r)", host, ip, server_hostname)
        return wrapped


def exchange(sock: socket.socket, request_bytes: bytes) -> Tuple[bytes, bytes, list, bool]:
    """在已连接的套接字上发送请求并读取一个完整响应。"""
    sock.sendall(request_bytes)
    rfile = sock.makefile("rb")
    try:
        return read_response(rfile)
    finally:
        rfile.close()