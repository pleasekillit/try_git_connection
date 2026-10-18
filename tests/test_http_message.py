"""HTTP/1.1 报文解析测试。"""
import io

from scripts.proxy.http_message import (
    framing,
    header_get,
    parse_head,
    read_body,
    read_head,
    read_response,
    rewrite_response_head,
)


def test_parse_head_start_line_and_headers():
    head = b"GET /path HTTP/1.1\r\nHost: a.com\r\nX-Test: 1"
    start_line, headers = parse_head(head)
    assert start_line == "GET /path HTTP/1.1"
    assert header_get(headers, "host") == "a.com"
    assert header_get(headers, "HOST") == "a.com"


def test_read_head_stops_at_blank_line():
    stream = io.BytesIO(b"GET / HTTP/1.1\r\nHost: a.com\r\n\r\nBODY")
    head = read_head(stream)
    assert head == b"GET / HTTP/1.1\r\nHost: a.com\r\n"
    assert stream.read() == b"BODY"


def test_read_body_content_length():
    stream = io.BytesIO(b"hello")
    assert read_body(stream, [("Content-Length", "5")]) == b"hello"


def test_read_body_chunked():
    stream = io.BytesIO(b"5\r\nhello\r\n0\r\n\r\n")
    assert read_body(stream, [("Transfer-Encoding", "chunked")]) == b"hello"


def test_framing_detection():
    assert framing([("Transfer-Encoding", "chunked")]) == "chunked"
    assert framing([("Content-Length", "3")]) == "length"
    assert framing([]) == "none"


def test_read_response_with_content_length():
    stream = io.BytesIO(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nhi")
    head, body, headers, close_after = read_response(stream)
    assert body == b"hi"
    assert close_after is False


def test_read_response_until_close():
    stream = io.BytesIO(b"HTTP/1.1 200 OK\r\n\r\nhi")
    _, body, _, close_after = read_response(stream)
    assert body == b"hi"
    assert close_after is True


def test_read_response_no_body_status():
    stream = io.BytesIO(b"HTTP/1.1 304 Not Modified\r\n\r\n")
    _, body, _, close_after = read_response(stream)
    assert body == b""
    assert close_after is False


def test_rewrite_response_head_replaces_chunked_with_length():
    head = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nContent-Type: text/plain\r\n"
    out = rewrite_response_head(head, [("Transfer-Encoding", "chunked")], 5)
    text = out.decode("latin-1")
    assert "Transfer-Encoding" not in text
    assert "Content-Length: 5\r\n" in text
    assert "Content-Type: text/plain\r\n" in text
    # 仍遵循 read_head 约定：以 CRLF 结尾、不含结束空行
    assert out.endswith(b"Content-Length: 5\r\n")
    assert b"\r\n\r\n" not in out


def test_rewrite_response_head_updates_stale_content_length():
    head = b"HTTP/1.1 200 OK\r\nContent-Length: 999\r\n"
    out = rewrite_response_head(head, [("Content-Length", "999")], 12)
    assert out.decode("latin-1").count("Content-Length") == 1
    assert out.endswith(b"Content-Length: 12\r\n")