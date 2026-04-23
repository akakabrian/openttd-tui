"""Minimal synthesised SFX. Silent if no player available."""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import tempfile
import time
import wave
from pathlib import Path


_SOUND_SPECS: dict[str, tuple[list[int], float, int, int]] = {
    "build":     ([880, 1320],    0.09, 5, 30),
    "click":     ([1500],         0.04, 2, 15),
    "demolish":  ([220, 110],     0.13, 5, 40),
    "deny":      ([300, 200],     0.18, 5, 60),
    "chime":     ([660, 880, 1100], 0.35, 20, 200),
    "horn":      ([440, 520],     0.20, 10, 100),
}


def _synth(freqs, duration, atk_ms, dcy_ms, sr=22_050):
    n = int(sr * duration)
    atk = min(int(sr * atk_ms / 1000), n // 2)
    dcy = min(int(sr * dcy_ms / 1000), n - atk)
    out = bytearray()
    for i in range(n):
        if i < atk:
            env = i / max(atk, 1)
        elif i > n - dcy:
            env = max(0.0, (n - i) / max(dcy, 1))
        else:
            env = 1.0
        t = i / sr
        s = sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
        out.extend(struct.pack("<h", int(s * env * 0.3 * 32767)))
    return bytes(out)


def _detect_player():
    for cmd in (["paplay"], ["aplay", "-q"], ["afplay"]):
        if shutil.which(cmd[0]):
            return cmd
    return None


class SoundBoard:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._player = _detect_player() if enabled else None
        self._paths: dict[str, Path] = {}
        self._tmp: tempfile.TemporaryDirectory | None = None
        self._last: dict[str, float] = {}
        self._gap = 0.15
        if enabled and self._player is None:
            self.enabled = False

    def _ensure(self, name: str) -> Path | None:
        if not self.enabled or name not in _SOUND_SPECS:
            return None
        if name in self._paths:
            return self._paths[name]
        if self._tmp is None:
            self._tmp = tempfile.TemporaryDirectory(prefix="openttd-sfx-")
        freqs, dur, a, d = _SOUND_SPECS[name]
        data = _synth(freqs, dur, a, d)
        p = Path(self._tmp.name) / f"{name}.wav"
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(22_050)
            w.writeframes(data)
        self._paths[name] = p
        return p

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        if now - self._last.get(name, 0.0) < self._gap:
            return
        self._last[name] = now
        p = self._ensure(name)
        if p is None or self._player is None:
            return
        try:
            subprocess.Popen(
                [*self._player, str(p)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (OSError, FileNotFoundError):
            self.enabled = False
