"""代理服务器：基于 ThreadingTCPServer 的多线程监听。"""
from __future__ import annotations

import logging
import socketserver
import threading
from typing import Optional

from .app import Application

logger = logging.getLogger(__name__)


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.server.app.handle(self.request, self.client_address)


class _ThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, app: Application) -> None:
        self.app = app
        super().__init__(address, _Handler)


class ProxyServer:
    """在后台线程中运行的本地 HTTP 代理。"""

    def __init__(self, app: Application, host: str, port: int) -> None:
        self._app = app
        self._host = host
        self._port = port
        self._server: Optional[_ThreadingTCPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._server = _ThreadingTCPServer((self._host, self._port), self._app)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="pyfastgithub-server", daemon=True
        )
        self._thread.start()
        logger.info("代理已监听 http://%s:%s", self._host, self._port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("代理已停止")