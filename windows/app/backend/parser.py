import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Parameter:
    name: str
    value: float
    min_val: float
    max_val: float
    description: str


@dataclass
class AppState:
    parameters: Dict[str, Parameter] = field(default_factory=dict)
    log_lines: List[Tuple[str, str]] = field(default_factory=list)
    status: str = "Initializing..."
    connected: bool = False
    conn_addr: str = ""
    max_log_lines: int = 200


_PARAM_LINE_RE = re.compile(
    r'^\|\s*([a-zA-Z_]\w*)\s*\|\s*([+-]?\d+(?:\.\d+)?)\s*\|\s*([+-]?\d+(?:\.\d+)?)\s*\|\s*([+-]?\d+(?:\.\d+)?)\s*\|\s*(.+?)\s*\|$'
)
_TABLE_SEP_RE = re.compile(r'^\+[-=]+\+$')
_TABLE_HEADER_RE = re.compile(r'^\|\s*Param\s*\|')
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


def parse_parameter_line(line: str) -> Optional[Parameter]:
    line = strip_ansi(line).strip()
    m = _PARAM_LINE_RE.match(line)
    if not m:
        return None
    name, val_str, min_str, max_str, desc = m.groups()
    try:
        return Parameter(
            name=name.strip(),
            value=float(val_str.strip()),
            min_val=float(min_str.strip()),
            max_val=float(max_str.strip()),
            description=desc.strip(),
        )
    except ValueError:
        return None


def is_table_separator(line: str) -> bool:
    line = strip_ansi(line).strip()
    return bool(_TABLE_SEP_RE.match(line) or _TABLE_HEADER_RE.match(line))
