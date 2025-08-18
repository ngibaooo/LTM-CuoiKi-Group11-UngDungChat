import asyncio
import threading
from typing import Callable, Optional

from .protocol import Protocol

class AsyncClient:
    def __init__(self, host: str, port: int, on_message: Callable[[dict], None], on_connect: Callable[[], None], on_disconnect: Callable[[], None]):
        self.host = host
        self.port = port
        self.on_message = on_message
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self):
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self._stop.set()
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._shutdown(), self.loop)
        if self.thread:
            self.thread.join(timeout=1.0)

    def send(self, message: dict):
        if not self.loop:
            return
        asyncio.run_coroutine_threadsafe(self._send(message), self.loop)

    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._connect_and_read())

    async def _shutdown(self):
        try:
            if self.writer:
                self.writer.close()
                await self.writer.wait_closed()
        finally:
            if self.loop:
                self.loop.stop()

    async def _connect_and_read(self):
        backoff = 1
        while not self._stop.is_set():
            try:
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
                self.on_connect()
                buffer = bytearray()
                while not self._stop.is_set():
                    data = await self.reader.read(4096)
                    if not data:
                        break
                    buffer.extend(data)
                    for msg in Protocol.unpack(buffer):
                        self.on_message(msg)
            except Exception:
                # im lặng reconnect
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10)
            finally:
                self.on_disconnect()

    async def _send(self, message: dict):
        if not self.writer:
            return
        try:
            self.writer.write(Protocol.pack(message))
            await self.writer.drain()
        except Exception:
            pass