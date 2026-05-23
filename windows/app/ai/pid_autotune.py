import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from app.backend.tcp_client import TcpWorker
from app.backend.parser import AppState


@dataclass
class TuningState:
    strategy: str = "Idle"
    progress: float = 0.0
    error: float = 0.0
    error_pct: float = 0.0
    trend: str = "--"
    eta_seconds: float = 0.0


def _sign(x: float) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class AITuner(QThread):
    state_changed = pyqtSignal(TuningState)
    history_added = pyqtSignal(int, str, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, tcp_worker: TcpWorker, state: AppState,
                 target_param: str, target_value: float,
                 overshoot_ratio: float, tunable_params: List[str]):
        super().__init__()
        self._tcp = tcp_worker
        self._state = state
        self._target_param = target_param
        self._target_value = target_value
        self._overshoot = overshoot_ratio
        self._tunable = tunable_params
        self._running = False

        self._error_history: deque = deque(maxlen=30)
        self._step = 0
        self._start_time = 0.0

        # PID coef groups to try
        self._pid_presets = [
            (50, 20, 5),
            (30, 15, 3),
            (80, 30, 8),
            (40, 10, 2),
            (60, 25, 5),
        ]
        self._preset_idx = 0
        self._settling_checks = 0

    def stop(self):
        self._running = False

    def run(self):
        self._running = True
        self._start_time = time.time()
        self._step = 0
        self._error_history.clear()
        self._preset_idx = 0
        self._settling_checks = 0

        self._emit_state("Starting...", 0.0, 0.0, "--")

        # Phase 1: try presets
        while self._running and self._preset_idx < len(self._pid_presets):
            kp, ki, kd = self._pid_presets[self._preset_idx]
            self._apply_params(kp, ki, kd)
            params_str = f"kp={kp}, ki={ki}, kd={kd}"

            settled, error = self._wait_settle(timeout=5.0)
            e_pct = abs(error) / max(abs(self._target_value), 1) * 100
            progress = (self._preset_idx + 1) / len(self._pid_presets)

            if settled:
                trend = "稳定" if e_pct < 5 else "偏差较大"
                result = f"稳定在 {self._read_current():.1f}, 误差 {error:.1f} ({e_pct:.1f}%)"
                if e_pct < 5:
                    result += " ✓"
                self._add_history(params_str, result)
                self._emit_state(f"预设 {self._preset_idx+1}/{len(self._pid_presets)}",
                                 progress, error, trend)

                if e_pct < 3:
                    break
            else:
                self._add_history(params_str, f"未收敛，误差 {e_pct:.1f}%")
                self._emit_state(f"预设 {self._preset_idx+1}/{len(self._pid_presets)}",
                                 progress, error, "不收敛")

            self._preset_idx += 1

        # Phase 2: hill-climb fine tune
        if self._running:
            self._hill_climb()

        self._running = False
        final_error = self._current_error()
        if abs(final_error) < self._target_value * 0.05:
            self.finished.emit(True, f"调参完成! 最终误差: {final_error:.1f}")
        else:
            self.finished.emit(False, f"调参结束。最终误差: {final_error:.1f}")

    def _hill_climb(self):
        direction = 1
        step_size = 10
        best_error = self._current_error()
        best_params = self._current_params()

        for i in range(20):
            if not self._running:
                break

            param_name = self._tunable[i % len(self._tunable)]
            current_val = self._get_param(param_name)
            new_val = _clamp(current_val + direction * step_size * 0.1 * current_val,
                             0.1, 10000)
            self._tcp.send(f"set {param_name} {new_val:.1f}")
            time.sleep(1.5)

            new_error = self._current_error()
            progress = 0.6 + 0.4 * (i / 20)
            trend = "收敛中" if new_error < best_error else "偏离中"

            self._emit_state("爬山法微调", progress, new_error, trend)

            if new_error < best_error:
                best_error = new_error
                self._add_history(f"{param_name}={new_val:.1f}",
                                  f"误差减小: {best_error:.1f}")
                step_size = min(step_size * 1.2, 50)
            else:
                self._tcp.send(f"set {param_name} {current_val:.1f}")
                direction *= -1
                step_size = max(step_size * 0.5, 1)

            if best_error < abs(self._target_value) * 0.02:
                break

    def _apply_params(self, kp, ki, kd):
        if "kp" in self._tunable:
            self._tcp.send(f"set kp {kp}")
            time.sleep(0.15)
        if "ki" in self._tunable:
            self._tcp.send(f"set ki {ki}")
            time.sleep(0.15)
        if "kd" in self._tunable:
            self._tcp.send(f"set kd {kd}")
            time.sleep(0.15)

    def _wait_settle(self, timeout: float) -> tuple:
        start = time.time()
        while self._running and (time.time() - start) < timeout:
            time.sleep(0.3)
            err = self._current_error()
            self._error_history.append(err)
            if len(self._error_history) >= 5:
                recent = list(self._error_history)[-5:]
                if max(abs(e) for e in recent) < abs(self._target_value) * 0.1:
                    return True, err
        return False, self._current_error()

    def _current_error(self) -> float:
        if self._target_param in self._state.parameters:
            return self._target_value - self._state.parameters[self._target_param].value
        return self._target_value

    def _read_current(self) -> float:
        if self._target_param in self._state.parameters:
            return self._state.parameters[self._target_param].value
        return 0.0

    def _get_param(self, name: str) -> float:
        p = self._state.parameters.get(name)
        return p.value if p else 0.0

    def _current_params(self) -> dict:
        return {n: self._get_param(n) for n in self._tunable}

    def _emit_state(self, strategy, progress, error, trend):
        target_abs = max(abs(self._target_value), 1)
        e_pct = abs(error) / target_abs * 100
        elapsed = time.time() - self._start_time
        if progress > 0 and progress < 1.0:
            eta = elapsed / progress * (1 - progress)
        else:
            eta = 0
        s = TuningState(strategy=strategy, progress=progress, error=error,
                        error_pct=e_pct, trend=trend, eta_seconds=eta)
        self.state_changed.emit(s)

    def _add_history(self, params: str, result: str):
        self._step += 1
        self.history_added.emit(self._step, params, result)
