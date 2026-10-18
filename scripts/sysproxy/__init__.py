"""系统层：设置/还原操作系统代理。"""

from .windows import SystemProxy, build_proxy_override, build_proxy_server

__all__ = ["SystemProxy", "build_proxy_override", "build_proxy_server"]