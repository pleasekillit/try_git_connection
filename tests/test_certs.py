"""证书生成测试：CA 生成/复用、域名证书由 CA 签发、SSLContext 缓存。"""
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509.oid import NameOID

from scripts.certs import CertAuthority


def test_ensure_creates_then_reuses(tmp_path):
    ca = CertAuthority(tmp_path)
    assert ca.ensure() is True
    assert ca.ca_cert_path.is_file()
    assert ca.ca_key_path.is_file()
    assert ca.ensure() is False  # 已存在不再生成


def test_ca_is_self_signed(tmp_path):
    ca = CertAuthority(tmp_path)
    ca.ensure()
    cert = x509.load_pem_x509_certificate(ca.ca_cert_path.read_bytes())
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "pyFastGithub"
    assert cert.issuer == cert.subject


def test_server_cert_signed_by_ca(tmp_path):
    ca = CertAuthority(tmp_path)
    ca.ensure()
    ca.server_context("github.com")

    chain = (tmp_path / "domains" / "github.com.crt").read_bytes()
    server_cert = x509.load_pem_x509_certificate(chain)
    ca_cert = x509.load_pem_x509_certificate(ca.ca_cert_path.read_bytes())

    # 用 CA 公钥验证域名证书签名
    ca_cert.public_key().verify(
        server_cert.signature,
        server_cert.tbs_certificate_bytes,
        padding.PKCS1v15(),
        server_cert.signature_hash_algorithm,
    )
    san = server_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "github.com" in san.get_values_for_type(x509.DNSName)


def test_server_context_is_cached(tmp_path):
    ca = CertAuthority(tmp_path)
    ca.ensure()
    first = ca.server_context("github.com")
    second = ca.server_context("github.com")
    assert first is second