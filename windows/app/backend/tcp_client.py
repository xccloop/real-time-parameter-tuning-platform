import socket
import select
import time
from datetime import datetime
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal

from app.backend.parser import AppState, parse_parameter_line


class TcpWorker(QThread):
    log_received = pyqtSignal(str, str)
    param_updated = pyqtSignal(str, object)
    connection_changed = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._sock: Optional[socket.socket] = None
        self._running = False

    def connect_to(self, host: str, port: int):
        if self._sock:
            self.disconnect()

        try:
            self._sock = socket.create_connection((host, port), timeout=5)
            self._sock.setblocking(False)
            self.state.connected = True
            self.state.conn_addr = f"{host}:{port}"
            self.state.status = f"Connected to {host}:{port}"
            self.connection_changed.emit(True, self.state.conn_addr)
            self._add_log(f"Connected to {host}:{port}")
            self._running = True
            self.start()
        except (socket.error, ValueError) as e:
            msg = f"Connection failed: {e}"
            self.error_occurred.emit(msg)
            self._add_log(f"[ERROR] {msg}")
            self.state.connected = False
            self.connection_changed.emit(False, "")

    def disconnect(self):
        self._running = False
        self.wait(2000)
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self.state.connected = False
        self.state.conn_addr = ""
        self.state.status = "Disconnected"
        self.connection_changed.emit(False, "")
        self._add_log("Disconnected")

    def send(self, text: str):
        if not self._sock or not self.state.connected:
            self.error_occurred.emit("Not connected!")
            return
        try:
            self._sock.sendall((text + '\r\n').encode('utf-8'))
            self._add_log(f">>> SENT: {text}")
        except Exception as e:
            self.error_occurred.emit(f"Send failed: {e}")
            self._add_log(f"[ERROR] Send failed: {e}")

    def run(self):
        buf = b""
        while self._running:
            try:
                if not self._sock:
                    break
                readable, _, _ = select.select([self._sock], [], [], 0.1)
                if self._sock in readable:
                    data = self._sock.recv(4096)
                    if not data:
                        self._add_log("[ERROR] TCP connection closed by remote")
                        self.state.connected = False
                        self.connection_changed.emit(False, "")
                        break
                    buf += data
                    while b'\n' in buf:
                        line_b, buf = buf.split(b'\n', 1)
                        self._process_line(line_b)
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                self._add_log(f"[ERROR] TCP read error: {e}")
                self.state.connected = False
                self.connection_changed.emit(False, "")
                break
            except Exception as e:
                self._add_log(f"[ERROR] Unexpected: {e}")
                time.sleep(0.1)

    def _process_line(self, line_bytes: bytes):
        try:
            line = line_bytes.decode('utf-8', errors='replace').rstrip('\r')
        except Exception:
            line = line_bytes.decode('latin-1', errors='replace').rstrip('\r')

        if not line:
            return

        self._add_log(line)

        param = parse_parameter_line(line)
        if param is not None:
            self.state.parameters[param.name] = param
            self.param_updated.emit(param.name, param)

    def _add_log(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.state.log_lines.append((ts, text))
        if len(self.state.log_lines) > self.state.max_log_lines:
            self.state.log_lines = self.state.log_lines[-self.state.max_log_lines:]
        self.log_received.emit(ts, text)
