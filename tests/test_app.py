"""代理应用层测试：请求重构与响应写出。"""
from scripts.config import AppConfig, DomainConfig, ResponseConfig
from scripts.proxy.app import Application, _build_request, _should_close, _split_host_port
from scripts.proxy.flow import FlowAnalyzer


class FakeSock:
    def __init__(self):
        self.data = b""

    def sendall(self, data: bytes) -> None:
        self.data += data


def _app() -> Application:
    return Application(AppConfig(), ca=None, upstream=None, flow=FlowAnalyzer())


def test_split_host_port():
    assert _split_host_port("github.com:443", 443) == ("github.com", 443)
    assert _split_host_port("github.com", 443) == ("github.com", 443)


def test_should_close_rules():
    assert _should_close({"connection": "close"}, "HTTP/1.1") is True
    assert _should_close({"connection": "keep-alive"}, "HTTP/1.1") is False
    assert _should_close({}, "HTTP/1.0") is True
    assert _should_close({"connection": "keep-alive"}, "HTTP/1.0") is False


def test_build_request_rewrites_hop_headers():
    headers = [
        ("Host", "a.com"),
        ("Proxy-Connection", "keep-alive"),
        ("Connection", "keep-alive"),
        ("Content-Length", "3"),
    ]
    data = _build_request("POST", "/x", headers, b"abc", "a.com")
    text = data.decode("latin-1")
    assert text.startswith("POST /x HTTP/1.1\r\n")
    assert "Proxy-Connection" not in text
    assert "Connection: close" in text
    assert text.lower().count("connection:") == 1
    assert text.endswith("abc")


def test_build_request_adds_host_when_missing():
    text = _build_request("GET", "/", [], b"", "a.com").decode("latin-1")
    assert "Host: a.com" in text


def test_write_configured_response():
    sock = FakeSock()
    cfg = DomainConfig(response=ResponseConfig(status_code=404, content_value="blocked"))
    _app()._write_configured_response(sock, cfg)
    assert sock.data.startswith(b"HTTP/1.1 404")
    assert b"Content-Length: 7" in sock.data
    assert sock.data.endswith(b"blocked")


def test_write_simple():
    sock = FakeSock()
    _app()._write_simple(sock, 502, "Bad Gateway")
    assert sock.data.startswith(b"HTTP/1.1 502 Bad Gateway")
    assert sock.data.endswith(b"Bad Gateway")