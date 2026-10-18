"""上游客户端 SSL 上下文测试。"""
import ssl

from scripts.config import DomainConfig
from scripts.proxy import build_client_ssl_context


def test_default_verifies_chain_without_hostname():
    context = build_client_ssl_context(DomainConfig())
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is False


def test_ignore_name_mismatch_disables_verification():
    context = build_client_ssl_context(DomainConfig(tls_ignore_name_mismatch=True))
    assert context.verify_mode == ssl.CERT_NONE
    assert context.check_hostname is False