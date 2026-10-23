import socket
import threading
from types import TracebackType
from typing import Self
from urllib.parse import urlsplit, urlunsplit

BUFFER_SIZE = 65536
# First byte of the Postgres simple-query and parse messages a client sends to run SQL.
QUERY_MESSAGE_TYPES = (b"Q", b"P")


class FreezableProxy:
    """TCP proxy to Postgres that can freeze, so the database hangs instead of refusing."""

    def __init__(self, database_url: str) -> None:
        parts = urlsplit(database_url)
        self._upstream = (parts.hostname or "localhost", parts.port or 5432)
        self._frozen = threading.Event()
        self._freeze_on_query = threading.Event()
        self._sockets: list[socket.socket] = []
        self._listener = socket.create_server(("127.0.0.1", 0))
        port = self._listener.getsockname()[1]
        netloc = f"{parts.username}:{parts.password}@127.0.0.1:{port}"
        self.url = urlunsplit(parts._replace(netloc=netloc))

    def freeze(self) -> None:
        self._frozen.set()

    def freeze_on_next_query(self) -> None:
        """Let connections open normally, then freeze once a client sends SQL."""
        self._freeze_on_query.set()

    def __enter__(self) -> Self:
        threading.Thread(target=self._accept_forever, daemon=True).start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        for connection in [self._listener, *self._sockets]:
            connection.close()

    def _accept_forever(self) -> None:
        while True:
            try:
                client, _ = self._listener.accept()
            except OSError:
                return
            upstream = socket.create_connection(self._upstream)
            self._sockets.extend([client, upstream])
            threading.Thread(target=self._pump, args=(client, upstream), daemon=True).start()
            threading.Thread(target=self._pump, args=(upstream, client), daemon=True).start()

    def _pump(self, source: socket.socket, target: socket.socket) -> None:
        while chunk := _receive(source):
            if self._freeze_on_query.is_set() and chunk.startswith(QUERY_MESSAGE_TYPES):
                self.freeze()
            if not self._frozen.is_set():
                target.sendall(chunk)

        # One side closed, so close the other too; otherwise Postgres keeps a backend open.
        target.close()


def _receive(connection: socket.socket) -> bytes:
    try:
        return connection.recv(BUFFER_SIZE)
    except OSError:
        return b""
