from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from bots.base_bot import Bot
from config import BotConfig, ColorProfile, ConfigManager


class WillowChopperLauncherBot(Bot):
    """Launch the standalone Willow Chopper repo from the Ticker UI."""

    name = "Willow Chopper"

    def __init__(self, config: Optional[BotConfig] = None) -> None:
        super().__init__()
        cfg_mgr = ConfigManager()
        self._cfg = config or cfg_mgr.get_current_preset()
        self._repo_dir = Path.home() / "Documents" / "GitHub" / "Willow Chopper"
        self._entrypoint = self._repo_dir / "main.py"
        self._child: Optional[subprocess.Popen] = None
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None

    def stop(self) -> None:
        super().stop()
        self._terminate_child()

    def run_loop(self) -> None:
        """
        This bot manages its own subprocess lifecycle in `_run()`.
        `run_loop()` exists only to satisfy the abstract Bot interface.
        """
        time.sleep(1.0)

    def _run(self) -> None:
        if os.path.exists("/tmp/osrs_bot_stop"):
            try:
                os.remove("/tmp/osrs_bot_stop")
            except OSError:
                pass

        self.log(f"Bot '{self.name}' started.")
        self.log("Launching standalone Willow Chopper process.")

        if not self._entrypoint.exists():
            self.log(f"ERROR: missing entrypoint at {self._entrypoint}")
            self._running.clear()
            self.log(f"Bot '{self.name}' stopped.")
            return

        try:
            self._write_bridge_config()
            self._launch_child()
            while self._running.is_set():
                if self.stop_if_runtime_elapsed(self._cfg):
                    break
                if os.path.exists("/tmp/osrs_bot_stop"):
                    self.log("Stop file detected — halting bot")
                    break
                if self._child is not None and self._child.poll() is not None:
                    self.log(f"Willow Chopper exited with code {self._child.returncode}")
                    break
                self.loops += 1
                time.sleep(1.0)
        except Exception as exc:
            self.log(f"ERROR launching Willow Chopper: {exc}")
        finally:
            self._terminate_child()
            self._running.clear()
            self.log(f"Bot '{self.name}' stopped.")

    def _launch_child(self) -> None:
        self._child = subprocess.Popen(
            [sys.executable, str(self._entrypoint)],
            cwd=str(self._repo_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if self._child.stdout is not None:
            self._stdout_thread = threading.Thread(
                target=self._pipe_output,
                args=(self._child.stdout, ""),
                daemon=True,
            )
            self._stdout_thread.start()
        if self._child.stderr is not None:
            self._stderr_thread = threading.Thread(
                target=self._pipe_output,
                args=(self._child.stderr, "[stderr] "),
                daemon=True,
            )
            self._stderr_thread.start()

    def _pipe_output(self, pipe, prefix: str) -> None:
        try:
            for line in pipe:
                line = line.rstrip()
                if line:
                    self.log(f"{prefix}{line}")
        finally:
            pipe.close()

    def _terminate_child(self) -> None:
        if self._child is None:
            return
        if self._child.poll() is None:
            self.log("Stopping Willow Chopper process...")
            self._child.terminate()
            try:
                self._child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.log("Force-killing Willow Chopper process.")
                self._child.kill()
                self._child.wait(timeout=3)
        self._child = None

    def _write_bridge_config(self) -> None:
        bridge_config = {
            "log_color": self._profile_dict(self._cfg.log_color),
            "tree_color": self._profile_dict(self._cfg.tree_color),
            "stump_color": self._profile_dict(self._cfg.stump_color),
            "stump_color2": self._profile_dict(self._cfg.stump_color2),
            "bank_booth_color": self._profile_dict(self._cfg.bank_booth_color),
            "min_blob_area": 35,
            "click_padding": 4,
            "loop_delay_min": self._cfg.min_delay,
            "loop_delay_max": self._cfg.max_delay,
            "stump_retry_min_seconds": 10.0,
            "stump_retry_max_seconds": 13.0,
            "no_stump_retry_min_seconds": 20.0,
            "no_stump_retry_max_seconds": 25.0,
            "debug_enabled": True,
            "debug_save_frames": False,
            "search_region": self._resolve_search_region(),
        }
        config_dir = Path.home() / ".willow_chopper"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "config.json"
        config_path.write_text(json.dumps(bridge_config, indent=2))
        self.log(
            "Synced Willow Chopper config from current preset "
            f"log_rgb=({self._cfg.log_color.r}, {self._cfg.log_color.g}, {self._cfg.log_color.b}) "
            f"log_tol={self._cfg.log_color.tolerance}; "
            f"tree_rgb=({self._cfg.tree_color.r}, {self._cfg.tree_color.g}, {self._cfg.tree_color.b}) "
            f"tree_tol={self._cfg.tree_color.tolerance}; "
            f"tree_enabled={self._cfg.tree_color.enabled}; "
            f"stump_enabled={self._cfg.stump_color.enabled or self._cfg.stump_color2.enabled}"
        )

    def _resolve_search_region(self) -> dict:
        script = (
            'tell application "System Events" to tell process "RuneLite" '
            'to get {position, size} of window 1'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                left, top, width, height = [int(value.strip()) for value in result.stdout.strip().split(",")]
                self.log(f"Using RuneLite window region=({left}, {top}, {width}, {height})")
                return {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                }
        except Exception as exc:
            self.log(f"RuneLite window lookup failed: {exc}")

        self.log("RuneLite window lookup unavailable; Willow Chopper will use monitor auto-detection.")
        return {
            "left": 0,
            "top": 0,
            "width": 0,
            "height": 0,
        }

    def _profile_dict(self, profile: ColorProfile) -> dict:
        return {
            "r": profile.r,
            "g": profile.g,
            "b": profile.b,
            "tolerance": profile.tolerance,
            "enabled": profile.enabled,
        }


WillowChopperLauncherBot.register()
