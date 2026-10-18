"""代理端到端集成测试：仅在 127.0.0.1 回环上进行，不访问外网。"""
import http.server
import socket
import threading

import pytest

from scripts.certs import CertAuthority
from scripts.config import AppConfig
from scripts.proxy import Application, FlowAnalyzer, ProxyServer


class _EchoHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler 约定
        body = b"hello"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # 静音
        pass


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _recv_all(sock: socket.socket) -> bytes:
    chunks = []
    while True:
        data = sock.recv(4096)
        if not data:
            break
        chunks.append(data)
    return b"".join(chunks)


@pytest.fixture
def origin_server():
    port = _free_port()
    server = http.server.HTTPServer(("127.0.0.1", port), _EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()
    server.server_close()


@pytest.fixture
def proxy(tmp_path, origin_server):
    config = AppConfig()
    config.proxy.port = _free_port()
    app = Application(config, CertAuthority(tmp_path), upstream=None, flow=FlowAnalyzer())
    server = ProxyServer(app, "127.0.0.1", config.proxy.port)
    server.start()
    yield config.proxy.port, origin_server
    server.stop()


def test_plain_http_proxy_forwarding(proxy):
    proxy_port, origin_port = proxy
    target = f"http://127.0.0.1:{origin_port}/"
    request = (
        f"GET {target} HTTP/1.1\r\nHost: 127.0.0.1:{origin_port}\r\nConnection: close\r\n\r\n"
    ).encode()

    with socket.create_connection(("127.0.0.1", proxy_port), timeout=5) as sock:
        sock.sendall(request)
        response = _recv_all(sock)

    assert response.startswith(b"HTTP/1.1 200")
    assert response.endswith(b"\r\n\r\nhello")


def test_connect_tunnel_for_unmatched_host(proxy):
    proxy_port, origin_port = proxy
    with socket.create_connection(("127.0.0.1", proxy_port), timeout=5) as sock:
        sock.sendall(f"CONNECT 127.0.0.1:{origin_port} HTTP/1.1\r\n\r\n".encode())
        head = sock.recv(1024)
        assert b"200" in head

        sock.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        response = _recv_all(sock)

    assert b"200 OK" in response
    assert response.endswith(b"\r\n\r\nhello")