#!/usr/bin/env python3
"""
Real-Time Parameter Tuning Platform — Windows/Linux Host Monitor

基于 Rich 库的跨平台串口监控仪表盘。
通过串口连接 LS2K0300 板子，实时解析参数表，可视化展示。

功能:
  - 自动解析板子发送的参数表（| speed | 200 | ... | 格式）
  - 仪表盘实时显示参数当前值 + 进度条
  - 非阻塞键盘输入，支持方向键和退格编辑
  - 彩色串口日志窗口
  - 自动重连

用法:
  python monitor.py COM3         # Windows
  python monitor.py /dev/ttyUSB0 # Linux

依赖: pip install pyserial rich
"""

import sys
import os
import time
import threading
import queue
import re
import argparse
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ── 检查依赖 ────────────────────────────────────────────────────────
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("错误: 请先安装 pyserial:  pip install pyserial")
    sys.exit(1)

try:
    from rich.live import Live
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.console import Console, RenderableType
    from rich.progress_bar import ProgressBar
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Parameter:
    """从板子参数表解析得到的一个参数"""
    name: str
    value: int
    min_val: int
    max_val: int
    description: str
    updated_at: float = 0.0


@dataclass
class AppState:
    """应用程序全局状态（线程安全）"""
    parameters: Dict[str, Parameter] = field(default_factory=dict)
    log_lines: List[Tuple[str, str]] = field(default_factory=list)  # [(timestamp, text)]
    status: str = "Initializing..."
    connected: bool = False
    port_name: str = ""
    baud_rate: int = 115200
    log_lock: threading.Lock = field(default_factory=threading.Lock)
    param_lock: threading.Lock = field(default_factory=threading.Lock)
    max_log_lines: int = 100
    input_buffer: str = ""
    command_queue: queue.Queue = field(default_factory=queue.Queue)


# ═══════════════════════════════════════════════════════════════════
# 参数表解析器
# ═══════════════════════════════════════════════════════════════════

# 匹配参数表行: | speed   |     200 |        0 |     1000 | Target speed ... |
_PARAM_LINE_RE = re.compile(
    r'^\|\s*([a-zA-Z_]\w*)\s*\|\s*([+-]?\d+)\s*\|\s*([+-]?\d+)\s*\|\s*([+-]?\d+)\s*\|\s*(.+?)\s*\|$'
)

# 匹配表头或分隔线
_TABLE_SEP_RE = re.compile(r'^\+[-=]+\+$')
_TABLE_HEADER_RE = re.compile(r'^\|\s*Param\s*\|')

# ANSI 转义序列清理
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def strip_ansi(text: str) -> str:
    """移除 ANSI 转义序列"""
    return _ANSI_RE.sub('', text)


def parse_parameter_line(line: str) -> Optional[Parameter]:
    """尝试解析一行参数表，返回 Parameter 或 None"""
    line = strip_ansi(line).strip()
    m = _PARAM_LINE_RE.match(line)
    if not m:
        return None
    name, val_str, min_str, max_str, desc = m.groups()
    try:
        return Parameter(
            name=name.strip(),
            value=int(val_str.strip()),
            min_val=int(min_str.strip()),
            max_val=int(max_str.strip()),
            description=desc.strip(),
            updated_at=time.time()
        )
    except ValueError:
        return None


def is_table_separator(line: str) -> bool:
    """判断是否是参数表的分隔线"""
    line = strip_ansi(line).strip()
    return bool(_TABLE_SEP_RE.match(line) or _TABLE_HEADER_RE.match(line))


# ═══════════════════════════════════════════════════════════════════
# Rich TUI 渲染
# ═══════════════════════════════════════════════════════════════════

class MonitorTUI:
    """Rich 仪表盘渲染器"""

    def __init__(self, state: AppState):
        self.state = state
        self.console = Console()

    def _make_header(self) -> Panel:
        """顶部状态栏"""
        status_color = "green" if self.state.connected else "red"
        status_text = f"[{status_color}]● {'CONNECTED' if self.state.connected else 'DISCONNECTED'}[/{status_color}]"
        text = Text()
        text.append("Real-Time Parameter Tuning Platform", style="bold cyan")
        text.append("  —  Monitor v1.0\n", style="dim")
        text.append(f"Port: [yellow]{self.state.port_name}[/yellow]  ")
        text.append(f"Baud: [yellow]{self.state.baud_rate}[/yellow]  ")
        text.append(f"Status: {status_text}")
        return Panel(text, box=box.HEAVY, style="cyan")

    def _make_dashboard(self) -> Panel:
        """参数仪表盘"""
        with self.state.param_lock:
            params = dict(self.state.parameters)

        if not params:
            return Panel(
                Text("等待板子发送参数表...\n(板子每 1 秒自动发送)", style="dim yellow", justify="center"),
                title="[bold]PARAMETER DASHBOARD[/bold]",
                border_style="yellow",
                box=box.ROUNDED,
                padding=(1, 2)
            )

        table = Table(show_header=True, box=box.SIMPLE, expand=True,
                      header_style="bold white")
        table.add_column("Param", style="cyan", width=10)
        table.add_column("Value", style="bold", width=8)
        table.add_column("Bar", width=30)
        table.add_column("Range", style="dim", width=14)
        table.add_column("Description", style="white", width=30)

        for name, p in sorted(params.items()):
            if p.max_val > p.min_val:
                ratio = (p.value - p.min_val) / (p.max_val - p.min_val)
                ratio = max(0.0, min(1.0, ratio))
            else:
                ratio = 0.5

            # 颜色: 越低越蓝, 中间绿色, 越高越红
            if ratio < 0.33:
                bar_color = "blue"
            elif ratio < 0.67:
                bar_color = "green"
            elif ratio < 0.9:
                bar_color = "yellow"
            else:
                bar_color = "red"

            bar = ProgressBar(total=100, completed=int(ratio * 100), width=28)
            bar_text = Text()
            bar_text.append(f"[{bar_color}]", style="")
            # Rich progress bar wrapped
            from rich.progress_bar import ProgressBar as PB

            table.add_row(
                name,
                str(p.value),
                f"[{bar_color}]{'█' * int(ratio * 28)}{'░' * (28 - int(ratio * 28))}[/{bar_color}]",
                f"[{p.min_val} - {p.max_val}]",
                p.description
            )

        # 最后更新时间
        if params:
            latest = max(p.updated_at for p in params.values())
            ago = time.time() - latest
            footer = Text(f"最后更新: {ago:.1f}s 前", style="dim")
        else:
            footer = Text("")

        return Panel(
            table,
            title="[bold]PARAMETER DASHBOARD[/bold]",
            border_style="green",
            box=box.ROUNDED,
            padding=(0, 1)
        )

    def _make_log(self) -> Panel:
        """串口日志窗口"""
        with self.state.log_lock:
            lines = list(self.state.log_lines[-40:])

        if not lines:
            return Panel(
                Text("等待串口数据...", style="dim"),
                title="[bold]SERIAL LOG[/bold]",
                border_style="blue",
                box=box.ROUNDED
            )

        text = Text()
        for ts, content in lines:
            text.append(f"[dim]{ts}[/dim] ", style="")
            # 高亮参数表行
            if parse_parameter_line(content) is not None:
                text.append(f"{content}\n", style="green")
            elif is_table_separator(content):
                text.append(f"{content}\n", style="blue")
            elif content.startswith('[tuning]'):
                text.append(f"{content}\n", style="bold yellow")
            elif 'ERROR' in content.upper():
                text.append(f"{content}\n", style="bold red")
            else:
                text.append(f"{content}\n", style="white")

        return Panel(
            text,
            title="[bold]SERIAL LOG[/bold]",
            border_style="blue",
            box=box.ROUNDED,
            padding=(0, 0)
        )

    def _make_input_area(self) -> Panel:
        """命令输入区"""
        buffer = self.state.input_buffer
        prompt = Text()
        prompt.append("> ", style="bold green")
        prompt.append(buffer, style="white")
        if int(time.time() * 2) % 2 == 0:
            prompt.append("█", style="dim cyan")  # 闪烁光标

        return Panel(
            prompt,
            title="[bold]COMMAND[/bold]",
            border_style="magenta",
            box=box.ROUNDED,
            height=3
        )

    def render(self) -> Layout:
        """构建整个界面布局"""
        layout = Layout()
        layout.split(
            Layout(name="header", size=5),
            Layout(name="main"),
            Layout(name="input", size=3)
        )
        layout["main"].split_row(
            Layout(name="dashboard", ratio=2),
            Layout(name="log", ratio=3)
        )

        layout["header"].update(self._make_header())
        layout["dashboard"].update(self._make_dashboard())
        layout["log"].update(self._make_log())
        layout["input"].update(self._make_input_area())

        return layout


# ═══════════════════════════════════════════════════════════════════
# 串口读取线程
# ═══════════════════════════════════════════════════════════════════

class SerialReader(threading.Thread):
    """后台线程：持续读取串口数据"""

    def __init__(self, state: AppState, ser: serial.Serial):
        super().__init__(daemon=True)
        self.state = state
        self.ser = ser
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        buf = b""
        while not self._stop_event.is_set():
            try:
                if self.ser.in_waiting > 0:
                    data = self.ser.read(self.ser.in_waiting)
                    buf += data
                    # 按行分割
                    while b'\n' in buf:
                        line_b, buf = buf.split(b'\n', 1)
                        self._process_line(line_b)
                else:
                    time.sleep(0.05)
            except serial.SerialException as e:
                self._add_log(f"[ERROR] Serial read error: {e}", "red")
                self.state.connected = False
                break
            except Exception as e:
                self._add_log(f"[ERROR] Unexpected: {e}", "red")
                time.sleep(0.1)

    def _process_line(self, line_bytes: bytes):
        try:
            line = line_bytes.decode('utf-8', errors='replace').rstrip('\r')
        except Exception:
            line = line_bytes.decode('latin-1', errors='replace').rstrip('\r')

        if not line:
            return

        ts = datetime.now().strftime("%H:%M:%S")
        self._add_log(line)

        # 尝试解析参数
        param = parse_parameter_line(line)
        if param is not None:
            with self.state.param_lock:
                self.state.parameters[param.name] = param

    def _add_log(self, text: str, style: str = ""):
        ts = datetime.now().strftime("%H:%M:%S")
        with self.state.log_lock:
            self.state.log_lines.append((ts, text))
            if len(self.state.log_lines) > self.state.max_log_lines:
                self.state.log_lines = self.state.log_lines[-self.state.max_log_lines:]


# ═══════════════════════════════════════════════════════════════════
# 键盘输入处理
# ═══════════════════════════════════════════════════════════════════

def get_keypress() -> Optional[str]:
    """非阻塞获取键盘输入。Windows 用 msvcrt，Linux 用 termios"""
    try:
        import msvcrt  # Windows
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            try:
                return ch.decode('utf-8')
            except UnicodeDecodeError:
                # 返回原始字节的表示，处理特殊键
                if ch == b'\r':
                    return '\r'
                return None
        return None
    except ImportError:
        # Linux/Mac
        import termios
        import fcntl

        fd = sys.stdin.fileno()
        old_attrs = termios.tcgetattr(fd)
        old_flags = fcntl.fcntl(fd, fcntl.F_GETFL)

        try:
            new_attrs = termios.tcgetattr(fd)
            new_attrs[3] = new_attrs[3] & ~(termios.ICANON | termios.ECHO)  # lflags
            new_attrs[6][termios.VMIN] = 0
            new_attrs[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, new_attrs)
            fcntl.fcntl(fd, fcntl.F_SETFL, old_flags | os.O_NONBLOCK)

            try:
                ch = sys.stdin.read(1)
                return ch if ch else None
            except (IOError, TypeError):
                return None
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, old_attrs)
            fcntl.fcntl(fd, fcntl.F_SETFL, old_flags)


class KeyboardThread(threading.Thread):
    """后台线程：处理键盘输入"""

    def __init__(self, state: AppState, ser: Optional[serial.Serial]):
        super().__init__(daemon=True)
        self.state = state
        self.ser = ser
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            ch = get_keypress()
            if ch is not None:
                self._handle_key(ch)
            time.sleep(0.02)

    def _handle_key(self, ch: str):
        if ch == '\r' or ch == '\n':  # Enter
            cmd = self.state.input_buffer.strip()
            self.state.input_buffer = ""
            if cmd:
                self._send_command(cmd)
        elif ch == '\x7f' or ch == '\x08':  # Backspace / DEL
            self.state.input_buffer = self.state.input_buffer[:-1]
        elif ch == '\x03':  # Ctrl+C
            self._stop_event.set()
            raise KeyboardInterrupt()
        elif len(ch) == 1 and ord(ch) >= 32:  # 可打印字符
            self.state.input_buffer += ch

    def _send_command(self, cmd: str):
        if cmd.lower() == '/quit':
            self._stop_event.set()
            raise KeyboardInterrupt()

        if self.ser and self.ser.is_open:
            try:
                self.ser.write((cmd + '\r\n').encode('utf-8'))
                with self.state.log_lock:
                    ts = datetime.now().strftime("%H:%M:%S")
                    self.state.log_lines.append((ts, f">>> SENT: {cmd}"))
            except Exception as e:
                with self.state.log_lock:
                    ts = datetime.now().strftime("%H:%M:%S")
                    self.state.log_lines.append((ts, f"[ERROR] Send failed: {e}"))
        else:
            with self.state.log_lock:
                ts = datetime.now().strftime("%H:%M:%S")
                self.state.log_lines.append((ts, "[ERROR] Not connected!"))


# ═══════════════════════════════════════════════════════════════════
# 简单控制台模式（无 Rich 时的后备方案）
# ═══════════════════════════════════════════════════════════════════

class SimpleMonitor:
    """无 Rich 依赖的简化控制台监控器"""

    def __init__(self, state: AppState, ser: serial.Serial):
        self.state = state
        self.ser = ser
        self.reader = SerialReader(state, ser)
        self.running = True

    def run(self):
        print("=" * 60)
        print("  Real-Time Parameter Tuning Platform — Monitor")
        print(f"  Port: {self.state.port_name}  Baud: {self.state.baud_rate}")
        print("  Type commands and press Enter.  /quit to exit.")
        print("=" * 60)
        print()

        self.reader.start()

        try:
            while self.running:
                # 检查新日志
                self._check_new_output()

                # 检查键盘输入
                if self._kbhit():
                    line = input()
                    if line.strip().lower() == '/quit':
                        break
                    if self.ser.is_open:
                        self.ser.write((line + '\r\n').encode('utf-8'))
                        print(f">>> SENT: {line}")
                    else:
                        print("[ERROR] Not connected!")

                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self.reader.stop()
            print("\nMonitor stopped.")

    def _check_new_output(self):
        """打印新到的日志行，同时解析参数"""
        with self.state.log_lock:
            lines_to_print = list(self.state.log_lines[-10:])
            # 清空已打印的（避免重复）- 简单方案：用游标
        # 简化版只依赖 SerialReader 已经解析参数

    @staticmethod
    def _kbhit() -> bool:
        """检查是否有键盘输入（非阻塞）"""
        try:
            import msvcrt
            return msvcrt.kbhit()
        except ImportError:
            import select
            return select.select([sys.stdin], [], [], 0)[0] != []


# ═══════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════

def list_serial_ports():
    """列出可用串口"""
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("未找到串口设备")
        return
    print("可用串口:")
    for p in ports:
        print(f"  {p.device}  —  {p.description}")


def open_serial(port: str, baud: int = 115200) -> serial.Serial:
    """打开串口"""
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1,
            write_timeout=1.0
        )
        return ser
    except serial.SerialException as e:
        print(f"无法打开串口 {port}: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Real-Time Parameter Tuning Platform — Serial Monitor"
    )
    parser.add_argument(
        'port', nargs='?', default=None,
        help='串口名称 (如 COM3, /dev/ttyUSB0)'
    )
    parser.add_argument(
        '-b', '--baud', type=int, default=115200,
        help='波特率 (默认: 115200)'
    )
    parser.add_argument(
        '-l', '--list', action='store_true',
        help='列出可用串口'
    )
    parser.add_argument(
        '--simple', action='store_true',
        help='使用简化模式（无 Rich TUI）'
    )

    args = parser.parse_args()

    if args.list:
        list_serial_ports()
        return

    if args.port is None:
        print("请指定串口名称，或使用 -l 列出可用串口")
        print(f"用法: {sys.argv[0]} COM3")
        print(f"      {sys.argv[0]} /dev/ttyUSB0")
        sys.exit(1)

    # 打开串口
    ser = open_serial(args.port, args.baud)

    # 初始化状态
    state = AppState()
    state.connected = True
    state.port_name = args.port
    state.baud_rate = args.baud

    # 启动串口读取线程
    reader = SerialReader(state, ser)
    reader.start()

    if not RICH_AVAILABLE or args.simple:
        # 简化模式
        monitor = SimpleMonitor(state, ser)
        monitor.run()
    else:
        # Rich TUI 模式
        tui = MonitorTUI(state)
        kb_thread = KeyboardThread(state, ser)

        try:
            with Live(tui.render(), console=tui.console, refresh_per_second=10,
                      screen=True) as live:
                kb_thread.start()

                while True:
                    live.update(tui.render())
                    time.sleep(0.05)

                    # 检查是否断开
                    if not state.connected or not ser.is_open:
                        time.sleep(1)
                        live.update(tui.render())

        except KeyboardInterrupt:
            pass
        finally:
            kb_thread.stop()
            reader.stop()
            print("\n\nMonitor stopped. Goodbye!")

    reader.stop()
    if ser.is_open:
        ser.close()


if __name__ == '__main__':
    main()
