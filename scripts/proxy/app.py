"""应用编排：解析客户端请求并按域名策略转发。

支持：
- ``CONNECT`` + 命中规则 -> HTTPS 中间人（MITM）
- ``CONNECT`` + 未命中   -> 纯 TCP 隧道
- 普通 HTTP 代理请求     -> 直接/定制转发
"""
from __future__ import annotations

import logging
import socket
import ssl
import threading
from typing import Dict, List, Tuple
from urllib.parse import urlsplit

from ..certs import CertAuthority
from ..config import AppConfig, DomainConfig
from .flow import FlowAnalyzer
from .http_message import (
    header_get,
    headers_to_dict,
    parse_head,
    read_body,
    read_head,
    rewrite_response_head,
)
from .upstream import Upstream, exchange

logger = logging.getLogger(__name__)

_CONNECT_OK = b"HTTP/1.1 200 Connection Established\r\n\r\n"
_REASONS = {200: "OK", 400: "Bad Request", 404: "Not Found", 502: "Bad Gateway"}


def _split_host_port(target: str, default_port: int) -> Tuple[str, int]:
    host, sep, port = target.rpartition(":")
    if sep and port.isdigit():
        return host, int(port)
    return target, default_port


def _should_close(headers: Dict[str, str], version: str) -> bool:
    connection = headers.get("connection", "").lower()
    if "close" in connection:
        return True
    if version.upper() == "HTTP/1.0" and "keep-alive" not in connection:
        return True
    return False


def _build_request(
    method: str, path: str, headers: List[Tuple[str, str]], body: bytes, host: str
) -> bytes:
    """重构发给上游的请求：丢弃逐跳头，强制 ``Connection: close``。"""
    lines = [f"{method} {path} HTTP/1.1"]
    has_host = False
    for name, value in headers:
        low = name.lower()
        if low in ("connection", "proxy-connection"):
            continue
        if low == "host":
            has_host = True
        lines.append(f"{name}: {value}")
    if not has_host:
        lines.append(f"Host: {host}")
    lines.append("Connection: close")
    head = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
    return head + body


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    """把 src 的数据拷贝到 dst，直到一端关闭。"""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


class Application:
    """代理服务的业务处理核心。"""

    def __init__(
        self,
        config: AppConfig,
        ca: CertAuthority,
        upstream: Upstream,
        flow: FlowAnalyzer,
    ) -> None:
        self._config = config
        self._ca = ca
        self._upstream = upstream
        self._flow = flow

    # ------------------------------------------------------------- 入口
    def handle(self, sock: socket.socket, addr) -> None:
        try:
            sock.settimeout(None)
            rfile = sock.makefile("rb")
            head = read_head(rfile)
            if not head:
                return
            start_line, headers = parse_head(head)
            parts = start_line.split()
            if len(parts) < 3:
                self._write_simple(sock, 400, "Bad Request")
                return
            method, target, version = parts[0], parts[1], parts[2]
            if method.upper() == "CONNECT":
                self._handle_connect(sock, target)
            else:
                self._handle_http(sock, method, target, version, headers, rfile)
        except (OSError, ssl.SSLError) as ex:
            logger.debug("连接处理异常 %s: %s", addr, ex)
        except Exception as ex:  # noqa: BLE001 - 单连接异常不影响服务
            logger.warning("未预期的异常 %s: %s", addr, ex)
        finally:
            try:
                sock.close()
            except OSError:
                pass

    # ----------------------------------------------------------- CONNECT
    def _handle_connect(self, sock: socket.socket, target: str) -> None:
        host, port = _split_host_port(target, 443)
        cfg = self._config.match(host)
        if cfg is None:
            self._tunnel(sock, host, port)
            return

        try:
            sock.sendall(_CONNECT_OK)
            tls_sock = self._ca.server_context(host).wrap_socket(sock, server_side=True)
        except (ssl.SSLError, OSError) as ex:
            logger.debug("MITM TLS 握手失败 %s: %s", host, ex)
            return

        try:
            self._serve_mitm(tls_sock, host, port, cfg)
        finally:
            try:
                tls_sock.close()
            except OSError:
                pass

    def _tunnel(self, sock: socket.socket, host: str, port: int) -> None:
        try:
            remote = socket.create_connection(
                (host, port), timeout=self._config.upstream.connect_timeout
            )
        except OSError as ex:
            logger.debug("隧道连接失败 %s:%s: %s", host, port, ex)
            self._write_simple(sock, 502, "Bad Gateway")
            return

        sock.sendall(_CONNECT_OK)
        forward = threading.Thread(target=_pipe, args=(sock, remote), daemon=True)
        backward = threading.Thread(target=_pipe, args=(remote, sock), daemon=True)
        forward.start()
        backward.start()
        forward.join()
        backward.join()
        remote.close()

    def _serve_mitm(self, tls_sock: ssl.SSLSocket, host: str, port: int, cfg: DomainConfig) -> None:
        rfile = tls_sock.makefile("rb")
        try:
            while True:
                head = read_head(rfile)
                if not head:
                    break
                start_line, headers = parse_head(head)
                parts = start_line.split()
                if len(parts) < 3:
                    break
                method, path, version = parts[0], parts[1], parts[2]
                body = read_body(rfile, headers)

                if cfg.response is not None:
                    self._write_configured_response(tls_sock, cfg)
                    break

                request_bytes = _build_request(method, path, headers, body, host)
                try:
                    up_sock = self._upstream.connect(host, port, use_tls=True, cfg=cfg)
                    resp_head, resp_body, resp_headers, close_after = exchange(
                        up_sock, request_bytes
                    )
                    up_sock.close()
                except OSError as ex:
                    logger.warning("上游请求失败 %s%s: %s", host, path, ex)
                    self._write_simple(tls_sock, 502, "Bad Gateway")
                    break

                self._flow.add_up(len(request_bytes))
                self._flow.add_down(len(resp_head) + len(resp_body))
                out_head = rewrite_response_head(resp_head, resp_headers, len(resp_body))
                tls_sock.sendall(out_head + b"\r\n" + resp_body)

                if close_after or _should_close(headers_to_dict(headers), version):
                    break
        finally:
            rfile.close()

    # -------------------------------------------------------- 普通 HTTP
    def _handle_http(
        self,
        sock: socket.socket,
        method: str,
        target: str,
        version: str,
        headers: List[Tuple[str, str]],
        rfile,
    ) -> None:
        parsed = urlsplit(target)
        host = parsed.hostname
        if not host:
            self._write_simple(sock, 400, "Bad Request")
            return

        use_tls = parsed.scheme == "https"
        port = parsed.port or (443 if use_tls else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        body = read_body(rfile, headers)

        cfg = self._config.match(host)
        if cfg is not None and cfg.response is not None:
            self._write_configured_response(sock, cfg)
            return

        request_bytes = _build_request(method, path, headers, body, host)
        try:
            if cfg is not None:
                up_sock = self._upstream.connect(host, port, use_tls=use_tls, cfg=cfg)
            else:
                up_sock = socket.create_connection(
                    (host, port), timeout=self._config.upstream.connect_timeout
                )
            resp_head, resp_body, resp_headers, _ = exchange(up_sock, request_bytes)
            up_sock.close()
        except OSError as ex:
            logger.warning("HTTP 转发失败 %s%s: %s", host, path, ex)
            self._write_simple(sock, 502, "Bad Gateway")
            return

        self._flow.add_up(len(request_bytes))
        self._flow.add_down(len(resp_head) + len(resp_body))
        out_head = rewrite_response_head(resp_head, resp_headers, len(resp_body))
        sock.sendall(out_head + b"\r\n" + resp_body)

    # ----------------------------------------------------------- 响应
    def _write_simple(self, sock: socket.socket, code: int, text: str) -> None:
        body = text.encode("utf-8")
        reason = _REASONS.get(code, "Error")
        head = (
            f"HTTP/1.1 {code} {reason}\r\n"
            "Content-Type: text/plain;charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("latin-1")
        try:
            sock.sendall(head + body)
        except OSError:
            pass

    def _write_configured_response(self, sock: socket.socket, cfg: DomainConfig) -> None:
        response = cfg.response
        body = (response.content_value or "").encode("utf-8") if response else b""
        code = response.status_code if response else 200
        content_type = response.content_type if response else "text/plain;charset=utf-8"
        reason = _REASONS.get(code, "OK")
        head = (
            f"HTTP/1.1 {code} {reason}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("latin-1")
        try:
            sock.sendall(head + body)
        except OSError:
            pass