"""IP 测速排序测试（不访问真实网络）。"""
import math
import socket

from scripts.config import SpeedTestConfig
from scripts.resolver import IpAddressService


class FakeDns:
    def __init__(self, mapping):
        self._mapping = mapping

    def resolve(self, host):
        return self._mapping.get(host, [])


def _service(mapping, max_ip_count=3):
    return IpAddressService(
        FakeDns(mapping), SpeedTestConfig(connect_timeout=1.0, max_ip_count=max_ip_count, cache_ttl=0.0)
    )


def test_sorted_by_latency_and_limited(monkeypatch):
    service = _service({"h": ["1.1.1.1", "2.2.2.2", "3.3.3.3"]}, max_ip_count=2)
    latency = {"1.1.1.1": 0.30, "2.2.2.2": 0.10, "3.3.3.3": 0.20}
    monkeypatch.setattr(service, "_test", lambda ip, port: latency[ip])
    assert service.get_addresses("h", 443) == ["2.2.2.2", "3.3.3.3"]


def test_unreachable_ips_filtered(monkeypatch):
    service = _service({"h": ["1.1.1.1", "2.2.2.2"]})
    latency = {"1.1.1.1": math.inf, "2.2.2.2": 0.5}
    monkeypatch.setattr(service, "_test", lambda ip, port: latency[ip])
    assert service.get_addresses("h", 443) == ["2.2.2.2"]


def test_empty_when_no_addresses():
    assert _service({}).get_addresses("h", 443) == []


def test_extra_ips_used_when_dns_unreachable(monkeypatch):
    """DNS 返回的 IP 全部不可达时，备用 IP 仍能被选中。"""
    service = _service({"h": ["1.1.1.1"]})
    latency = {"1.1.1.1": math.inf, "9.9.9.9": 0.2}
    monkeypatch.setattr(service, "_test", lambda ip, port: latency[ip])
    assert service.get_addresses("h", 443, ["9.9.9.9"]) == ["9.9.9.9"]


def test_extra_ips_merged_and_deduplicated(monkeypatch):
    """备用 IP 与 DNS 结果合并去重后按延迟排序。"""
    service = _service({"h": ["1.1.1.1"]})
    latency = {"1.1.1.1": 0.3, "2.2.2.2": 0.1}
    seen = []

    def fake_test(ip, port):
        seen.append(ip)
        return latency[ip]

    monkeypatch.setattr(service, "_test", fake_test)
    assert service.get_addresses("h", 443, ["1.1.1.1", "2.2.2.2"]) == ["2.2.2.2", "1.1.1.1"]
    assert sorted(seen) == ["1.1.1.1", "2.2.2.2"]


def test_test_returns_inf_on_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(socket, "create_connection", boom)
    service = _service({})
    assert math.isinf(service._test("1.1.1.1", 443))