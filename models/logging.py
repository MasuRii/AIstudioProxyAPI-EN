import asyncio
import datetime
import json
import logging
import sys
from typing import Dict, List

from fastapi import WebSocket, WebSocketDisconnect


class StreamToLogger:
    def __init__(self, logger_instance: logging.Logger, log_level: int = logging.INFO):
        self.logger = logger_instance
        self.log_level = log_level
        self.linebuf = ""

    def write(self, buf: str):
        try:
            temp_linebuf = self.linebuf + buf
            self.linebuf = ""
            for line in temp_linebuf.splitlines(True):
                if line.endswith(("\n", "\r")):
                    self.logger.log(self.log_level, line.rstrip())
                else:
                    self.linebuf += line
        except Exception as e:
            print(f"StreamToLogger Error: {e}", file=sys.__stderr__)

    def flush(self):
        try:
            if self.linebuf != "":
                self.logger.log(self.log_level, self.linebuf.rstrip())
            self.linebuf = ""
        except Exception as e:
            print(f"StreamToLogger Flush Error: {e}", file=sys.__stderr__)

    def isatty(self):
        return False


class WebSocketConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger = logging.getLogger("AIStudioProxyServer")
        logger.info(f"WebSocket logging client connected: {client_id}")
        try:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "connection_status",
                        "status": "connected",
                        "message": "Connected to real-time log stream.",
                        "timestamp": datetime.datetime.now().isoformat(),
                    }
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Failed to send welcome message to WebSocket client {client_id}: {e}")

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger = logging.getLogger("AIStudioProxyServer")
            logger.info(f"WebSocket logging client disconnected: {client_id}")

    async def broadcast(self, message: str):
        if not self.active_connections:
            return
        disconnected_clients: List[str] = []
        active_conns_copy = list(self.active_connections.items())
        logger = logging.getLogger("AIStudioProxyServer")
        for client_id, connection in active_conns_copy:
            try:
                await connection.send_text(message)
            except WebSocketDisconnect:
                logger.info(f"[WS Broadcast] Client {client_id} disconnected during broadcast.")
                disconnected_clients.append(client_id)
            except RuntimeError as e:
                if "Connection is closed" in str(e):
                    logger.info(f"[WS Broadcast] Connection for client {client_id} is closed.")
                    disconnected_clients.append(client_id)
                else:
                    logger.error(f"Runtime error broadcasting to WebSocket {client_id}: {e}")
                    disconnected_clients.append(client_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Unknown error broadcasting to WebSocket {client_id}: {e}")
                disconnected_clients.append(client_id)
        if disconnected_clients:
            for client_id_to_remove in disconnected_clients:
                self.disconnect(client_id_to_remove)


class WebSocketLogHandler(logging.Handler):
    def __init__(self, manager: WebSocketConnectionManager):
        super().__init__()
        self.manager = manager
        self.formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    def emit(self, record: logging.LogRecord):
        if self.manager and self.manager.active_connections:
            try:
                log_entry_str = self.format(record)
                try:
                    current_loop = asyncio.get_running_loop()
                    current_loop.create_task(self.manager.broadcast(log_entry_str))
                except RuntimeError:
                    pass
            except Exception as e:
                print(f"WebSocketLogHandler Error: Failed to broadcast log - {e}", file=sys.__stderr__)
