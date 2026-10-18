"""Windows 系统代理设置与还原（写注册表 + 通知系统刷新）。

非 Windows 平台下 ``SystemProxy.enable/restore`` 为空操作。
"""
from __future__ import annotations

import logging
import sys
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
_OPTION_REFRESH = 37
_OPTION_SETTINGS_CHANGED = 39
_LOCAL_BYPASS = "127.0.0.1;localhost;<local>"


def is_windows() -> bool:
    return sys.platform.startswith("win")


def build_proxy_server(host: str, port: int) -> str:
    """构造 ProxyServer 注册表值。"""
    return f"{host}:{port}"


def build_proxy_override(existing: Optional[str]) -> str:
    """在已有例外基础上追加本地地址，避免自代理死循环。"""
    if not existing:
        return _LOCAL_BYPASS
    if "<local>" in existing:
        return existing
    return f"{existing};{_LOCAL_BYPASS}"


class SystemProxy:
    """记录原设置并在退出时还原。"""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._snapshot: Optional[Dict[str, object]] = None

    def enable(self) -> bool:
        if not is_windows():
            logger.warning(
                "当前平台不支持自动设置系统代理，请手动配置 HTTP 代理 %s:%s", self._host, self._port
            )
            return False

        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_READ | winreg.KEY_WRITE
            ) as key:
                self._snapshot = _read_snapshot(key)
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(
                    key, "ProxyServer", 0, winreg.REG_SZ, build_proxy_server(self._host, self._port)
                )
                winreg.SetValueEx(
                    key,
                    "ProxyOverride",
                    0,
                    winreg.REG_SZ,
                    build_proxy_override(self._snapshot["proxy_override"]),
                )
        except OSError as ex:
            logger.warning("设置系统代理失败: %s", ex)
            return False

        _notify_refresh()
        logger.info("系统代理已设置: %s:%s", self._host, self._port)
        return True

    def restore(self) -> None:
        if not is_windows() or self._snapshot is None:
            return

        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(
                    key, "ProxyEnable", 0, winreg.REG_DWORD, int(self._snapshot["proxy_enable"])
                )
                winreg.SetValueEx(
                    key, "ProxyServer", 0, winreg.REG_SZ, str(self._snapshot["proxy_server"] or "")
                )
                winreg.SetValueEx(
                    key, "ProxyOverride", 0, winreg.REG_SZ, str(self._snapshot["proxy_override"] or "")
                )
        except OSError as ex:
            logger.warning("还原系统代理失败: %s", ex)
            return

        _notify_refresh()
        logger.info("系统代理已还原")


def _read_snapshot(key) -> Dict[str, object]:
    return {
        "proxy_enable": _read_value(key, "ProxyEnable", 0),
        "proxy_server": _read_value(key, "ProxyServer", None),
        "proxy_override": _read_value(key, "ProxyOverride", None),
    }


def _read_value(key, name: str, default):
    import winreg

    try:
        value, _ = winreg.QueryValueEx(key, name)
        return value
    except FileNotFoundError:
        return default


def _notify_refresh() -> None:
    try:
        import ctypes

        wininet = ctypes.windll.wininet
        wininet.InternetSetOptionW(0, _OPTION_SETTINGS_CHANGED, 0, 0)
        wininet.InternetSetOptionW(0, _OPTION_REFRESH, 0, 0)
    except (OSError, AttributeError) as ex:
        logger.debug("刷新系统代理失败: %s", ex)