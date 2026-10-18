"""系统代理纯函数测试（不触碰注册表）。"""
from scripts.sysproxy import build_proxy_override, build_proxy_server


def test_build_proxy_server():
    assert build_proxy_server("127.0.0.1", 38457) == "127.0.0.1:38457"


def test_build_proxy_override_default():
    result = build_proxy_override(None)
    assert "127.0.0.1" in result
    assert "<local>" in result


def test_build_proxy_override_merges_existing():
    result = build_proxy_override("example.com")
    assert "example.com" in result
    assert "<local>" in result


def test_build_proxy_override_keeps_local_marker():
    assert build_proxy_override("a.com;<local>") == "a.com;<local>"