"""SNI 表达式测试。"""
from scripts.config import DomainConfig
from scripts.config.models import SniPattern


def test_default_sni_uses_domain():
    cfg = DomainConfig()
    pattern = cfg.sni_pattern()
    assert pattern.value == SniPattern.DOMAIN
    assert pattern.with_domain("github.com").value == "github.com"
    assert pattern.with_domain("a.com").enabled


def test_tls_sni_disabled_means_empty():
    cfg = DomainConfig(tls_sni=False)
    assert cfg.sni_pattern().value == ""
    assert not cfg.sni_pattern().enabled


def test_custom_pattern_with_ip():
    cfg = DomainConfig(tls_sni_pattern="@ipaddress")
    assert cfg.sni_pattern().with_ip("1.2.3.4").value == "1.2.3.4"


def test_custom_pattern_with_random():
    value = SniPattern("@random").with_random().value
    assert value.isdigit()


def test_combined_pattern():
    cfg = DomainConfig(tls_sni_pattern="@domain.@random")
    value = cfg.sni_pattern().with_domain("x.com").with_random().value
    assert value.startswith("x.com.")