"""自签 CA 与域名服务器证书的生成、持久化与复用。

- CA 证书/私钥：``<ca_dir>/pyfastgithub.crt`` / ``pyfastgithub.key``
- 域名证书：``<ca_dir>/domains/<safe>.crt`` / ``<safe>.key``
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import ssl
from pathlib import Path
from typing import Dict

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .installer import install_ca

logger = logging.getLogger(__name__)

_ONE_DAY = dt.timedelta(days=1)


class CertAuthority:
    """管理 CA 与各域名的服务器证书。"""

    def __init__(self, ca_dir: str | Path) -> None:
        self.ca_dir = Path(ca_dir)
        self.ca_cert_path = self.ca_dir / "pyfastgithub.crt"
        self.ca_key_path = self.ca_dir / "pyfastgithub.key"
        self._domains_dir = self.ca_dir / "domains"
        self._contexts: Dict[str, ssl.SSLContext] = {}
        self._ca_cert: x509.Certificate | None = None
        self._ca_key: rsa.RSAPrivateKey | None = None

    # ------------------------------------------------------------------ CA
    def ensure(self) -> bool:
        """确保 CA 存在；新生成时返回 True。"""
        self.ca_dir.mkdir(parents=True, exist_ok=True)
        if self.ca_cert_path.is_file() and self.ca_key_path.is_file():
            return False

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "pyFastGithub")])
        now = dt.datetime.now(dt.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - _ONE_DAY)
            .not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(key, hashes.SHA256())
        )

        self.ca_key_path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        self.ca_cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        logger.info("已生成 CA 证书: %s", self.ca_cert_path)
        return True

    def install_ca(self) -> bool:
        self.ensure()
        return install_ca(self.ca_cert_path)

    # ------------------------------------------------------- 域名服务器证书
    def server_context(self, domain: str) -> ssl.SSLContext:
        """返回加载了该域名证书的服务端 SSLContext（带缓存）。"""
        cached = self._contexts.get(domain)
        if cached is not None:
            return cached

        cert_path, key_path = self._get_or_create_domain_cert(domain)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert_path), str(key_path))
        self._contexts[domain] = context
        return context

    def _get_or_create_domain_cert(self, domain: str) -> tuple[Path, Path]:
        self._domains_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^0-9A-Za-z._-]", "_", domain)
        cert_path = self._domains_dir / f"{safe}.crt"
        key_path = self._domains_dir / f"{safe}.key"
        if cert_path.is_file() and key_path.is_file():
            return cert_path, key_path

        ca_cert, ca_key = self._load_ca()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = dt.datetime.now(dt.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - _ONE_DAY)
            .not_valid_after(now + dt.timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
            )
            .sign(ca_key, hashes.SHA256())
        )

        key_path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        # 证书链：域名证书 + CA 证书，便于客户端构建完整链路
        chain = cert.public_bytes(serialization.Encoding.PEM) + ca_cert.public_bytes(
            serialization.Encoding.PEM
        )
        cert_path.write_bytes(chain)
        return cert_path, key_path

    def _load_ca(self) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
        if self._ca_cert is None:
            self._ca_cert = x509.load_pem_x509_certificate(self.ca_cert_path.read_bytes())
        if self._ca_key is None:
            self._ca_key = serialization.load_pem_private_key(
                self.ca_key_path.read_bytes(), password=None
            )
        return self._ca_cert, self._ca_key