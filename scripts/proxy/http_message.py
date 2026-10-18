"""HTTP/1.1 报文的读取与解析。

约定：``read_head`` 返回的 head **不含**结束的空行；
回写时需自行补 ``\\r\\n\\r\\n``。
"""
from __future__ import annotations

from typing import Dict, List, Tuple

CRLF = b"\r\n"
_HEAD_END = b"\r\n\r\n"


def read_head(rfile) -> bytes:
    """读取到空行为止（空行不包含在返回值中）。"""
    lines: List[bytes] = []
    while True:
        line = rfile.readline()
        if not line:
            break
        if line in (b"\r\n", b"\n"):
            break
        lines.append(line)
    return b"".join(lines)


def parse_head(head: bytes) -> Tuple[str, List[Tuple[str, str]]]:
    """解析请求/响应头，返回 (起始行, [(名称, 值), ...])。"""
    text = head.decode("latin-1").replace("\r\n", "\n")
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return "", []
    start_line = lines[0]
    headers: List[Tuple[str, str]] = []
    for line in lines[1:]:
        name, _, value = line.partition(":")
        headers.append((name.strip(), value.strip()))
    return start_line, headers


def header_get(headers: List[Tuple[str, str]], name: str) -> str | None:
    """按名称取头（忽略大小写）。"""
    target = name.lower()
    for key, value in headers:
        if key.lower() == target:
            return value
    return None


def headers_to_dict(headers: List[Tuple[str, str]]) -> Dict[str, str]:
    return {key.lower(): value for key, value in headers}


def framing(headers: List[Tuple[str, str]]) -> str:
    """返回正文的成帧方式：``chunked`` / ``length`` / ``none``。"""
    te = header_get(headers, "transfer-encoding")
    if te and "chunked" in te.lower():
        return "chunked"
    if header_get(headers, "content-length") is not None:
        return "length"
    return "none"


def read_chunked(rfile) -> bytes:
    """读取 chunked 正文。"""
    out = bytearray()
    while True:
        size_line = rfile.readline()
        if not size_line:
            break
        size_token = size_line.split(b";")[0].strip()
        try:
            size = int(size_token, 16)
        except ValueError:
            break
        if size == 0:
            # 读掉结束块（以及可能的 trailer）
            while True:
                trailer = rfile.readline()
                if not trailer or trailer in (b"\r\n", b"\n"):
                    break
            break
        chunk = rfile.read(size)
        if chunk:
            out.extend(chunk)
        rfile.readline()  # 块尾 CRLF
    return bytes(out)


def read_body(rfile, headers: List[Tuple[str, str]], until_close: bool = False) -> bytes:
    """读取正文。``until_close`` 为真时（无 Content-Length 的响应）读到 EOF。"""
    mode = framing(headers)
    if mode == "chunked":
        return read_chunked(rfile)
    if mode == "length":
        try:
            length = int(header_get(headers, "content-length") or 0)
        except ValueError:
            return b""
        return rfile.read(length) if length > 0 else b""
    if until_close:
        return rfile.read() or b""
    return b""


def read_response(rfile) -> Tuple[bytes, bytes, List[Tuple[str, str]], bool]:
    """读取一个响应。

    返回 ``(head, body, headers, close_after)``。
    ``close_after`` 表示响应无成帧信息、以关闭连接结束（需关闭客户端连接）。
    """
    head = read_head(rfile)
    start_line, headers = parse_head(head)
    status_code = _status_code(start_line)

    if status_code is not None and (100 <= status_code < 200 or status_code in (204, 304)):
        return head, b"", headers, False

    close_after = framing(headers) == "none"
    body = read_body(rfile, headers, until_close=close_after)
    return head, body, headers, close_after


def _status_code(start_line: str) -> int | None:
    parts = start_line.split()
    if len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])
    return None


def rewrite_response_head(
    head: bytes, headers: List[Tuple[str, str]], body_len: int
) -> bytes:
    """改写上游响应头，使其与已解码的正文匹配。

    正文在转发前已被解码（chunked 拆包），因此必须去掉 ``Transfer-Encoding``
    并写入准确的 ``Content-Length``，否则客户端会按 chunked 解析导致失败。
    返回值遵循 ``read_head`` 约定：包含各行的 CRLF、不含结束空行。
    """
    text = head.decode("latin-1").replace("\r\n", "\n")
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return head
    out = [lines[0]]
    for line in lines[1:]:
        name = line.split(":", 1)[0].strip().lower()
        if name in ("transfer-encoding", "content-length"):
            continue
        out.append(line)
    out.append(f"Content-Length: {body_len}")
    return ("\r\n".join(out) + "\r\n").encode("latin-1")