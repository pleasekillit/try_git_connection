"""在 Windows 受信任根证书存储中安装/检查自签 CA。"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def is_windows() -> bool:
    return sys.platform.startswith("win")


def install_ca(cer_path: str | Path) -> bool:
    """把 CA 证书安装到**当前用户**的"受信任的根证书颁发机构"。

    使用 ``certutil -user``，无需管理员权限。
    非 Windows 平台返回 False；调用方应提示用户手动信任。
    """
    if not is_windows():
        logger.warning("当前平台不支持自动安装 CA，请手动信任证书: %s", cer_path)
        return False

    cer_path = str(cer_path)
    try:
        completed = subprocess.run(
            ["certutil", "-user", "-addstore", "-f", "Root", cer_path],
            capture_output=True,
            check=False,
        )
    except OSError as ex:  # certutil 不存在等
        logger.warning("调用 certutil 失败: %s", ex)
        return False

    if completed.returncode != 0:
        logger.warning("安装 CA 失败: %s", _decode(completed.stderr or completed.stdout))
        return False

    logger.info("CA 证书已安装到受信任根证书存储: %s", cer_path)
    return True


def _decode(data: bytes) -> str:
    """certutil 在中文 Windows 输出 GBK，这里容错解码。"""
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace").strip()