"""命令行入口。

用法：
    python -m scripts run [--listen 127.0.0.1] [--port 38457] [--no-system-proxy]
    python -m scripts install-ca
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from .certs import CertAuthority
from .config import AppConfig, load_config
from .proxy import Application, FlowAnalyzer, ProxyServer, Upstream
from .resolver import DnsClient, DomainResolver, IpAddressService
from .sysproxy import SystemProxy
from .utils.logging import setup_logging

logger = logging.getLogger("pyfastgithub")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA_DIR = _PROJECT_ROOT / "data"
_DEFAULT_CA_DIR = _PROJECT_ROOT / "cacert"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfastgithub", description="GitHub 访问加速（本地 HTTP 代理 + HTTPS 中间人）"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="启动代理服务")
    _add_common(run)
    run.add_argument("--listen", default=None, help="监听地址（覆盖配置）")
    run.add_argument("--port", type=int, default=None, help="监听端口（覆盖配置）")
    run.add_argument("--no-system-proxy", action="store_true", help="不自动设置系统代理")
    run.set_defaults(func=cmd_run)

    install = sub.add_parser("install-ca", help="生成并安装 CA 证书")
    _add_common(install)
    install.set_defaults(func=cmd_install_ca)

    return parser


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-dir", default=str(_DEFAULT_DATA_DIR), help="配置数据目录（默认 data/）")
    parser.add_argument("--ca-dir", default=str(_DEFAULT_CA_DIR), help="CA 与证书目录（默认 cacert/）")
    parser.add_argument("--log-level", default="INFO", help="日志级别（默认 INFO）")


def cmd_install_ca(args) -> int:
    setup_logging(args.log_level)
    ca = CertAuthority(args.ca_dir)
    created = ca.ensure()
    logger.info("CA 已%s: %s", "生成" if created else "存在", ca.ca_cert_path)
    if ca.install_ca():
        return 0
    logger.error("CA 安装失败：请以管理员身份运行，或手动信任证书 %s", ca.ca_cert_path)
    return 1


def _build_app(config: AppConfig, ca_dir: str):
    dns = DnsClient(config.dns)
    ip_service = IpAddressService(dns, config.speed_test)
    resolver = DomainResolver(ip_service, config.speed_test.cache_ttl)
    upstream = Upstream(resolver, config.upstream)
    flow = FlowAnalyzer()
    ca = CertAuthority(ca_dir)
    ca.ensure()
    app = Application(config, ca, upstream, flow)
    return app, flow


def cmd_run(args) -> int:
    setup_logging(args.log_level)
    try:
        config = load_config(args.data_dir)
    except (OSError, ValueError) as ex:
        logger.error("加载配置失败: %s", ex)
        return 1

    if args.listen:
        config.proxy.listen = args.listen
    if args.port:
        config.proxy.port = args.port
    logger.info("已加载配置: %d 条域名规则, 代理 %s:%s", len(config.domains), config.proxy.listen, config.proxy.port)

    app, flow = _build_app(config, args.ca_dir)

    server = ProxyServer(app, config.proxy.listen, config.proxy.port)
    try:
        server.start()
    except OSError as ex:
        logger.error("启动代理失败: %s", ex)
        return 1

    system_proxy = None
    if args.no_system_proxy:
        logger.info("已跳过系统代理设置（--no-system-proxy）")
    else:
        system_proxy = SystemProxy(config.proxy.listen, config.proxy.port)
        system_proxy.enable()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到中断，正在退出...")
    finally:
        if system_proxy is not None:
            system_proxy.restore()
        server.stop()
        stats = flow.snapshot()
        logger.info("本次流量: 上行 %d 字节 / 下行 %d 字节", stats["up"], stats["down"])
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())