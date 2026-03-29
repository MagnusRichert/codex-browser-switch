import asyncio
import ctypes
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil
import win32gui
import win32process
import win32com.client
from flask import Flask, redirect, render_template_string, request

try:
    from winrt.windows.ui.notifications import NotificationKinds
    from winrt.windows.ui.notifications.management import (
        UserNotificationListener,
        UserNotificationListenerAccessStatus,
    )
except ImportError:
    NotificationKinds = None
    UserNotificationListener = None
    UserNotificationListenerAccessStatus = None


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
DEFAULT_CONFIG = {
    "poll_interval_seconds": 0.8,
    "switch_back_timeout_seconds": 120,
    "dedupe_window_seconds": 8,
    "heartbeat_interval_seconds": 30,
    "switch_strategy": "alt_tab",
    "switch_delay_seconds": 0.15,
    "switch_to_sendkeys": "",
    "switch_back_sendkeys": "",
    "web_host": "127.0.0.1",
    "web_port": 5057,
    "browser_process_names": ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "arc.exe"],
    "codex_process_names": ["codex.exe", "codex"],
    "codex_log_db_path": str(Path.home() / ".codex" / "logs_1.sqlite"),
    "debug_log_path": str(ROOT / "codex_yt_switch.log"),
    "switch_back_substrings": [
        'received message {"type":"response.created"',
    ],
    "codex_notification_app_substrings": ["codex"],
    "switch_back_hotkeys": ["1", "2"],
}


@dataclass
class PendingReturn:
    browser_hwnd: int
    activated_at: float


LOGGER = logging.getLogger("codex_yt_switch")
WEB_APP = Flask(__name__)
SETTINGS_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex YT Switch Settings</title>
  <style>
    :root { color-scheme: light; --bg:#f6f3ee; --card:#fffdf8; --ink:#1e1b18; --accent:#b45309; --line:#e7dccd; }
    body { margin:0; font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif; background:linear-gradient(135deg,#f6f3ee,#efe6d8); color:var(--ink); }
    .wrap { max-width:1280px; margin:40px auto; padding:24px; }
    .layout { display:grid; grid-template-columns:minmax(0, 1.1fr) minmax(380px, 0.9fr); gap:24px; align-items:start; }
    .card { background:var(--card); border:1px solid var(--line); border-radius:18px; padding:24px; box-shadow:0 18px 50px rgba(73,45,18,.08); }
    h1 { margin:0 0 8px; font-size:34px; }
    h2 { margin:0 0 10px; font-size:24px; }
    p { line-height:1.5; }
    .grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
    label { display:block; font-weight:700; margin-bottom:6px; }
    input, select { width:100%; padding:10px 12px; border-radius:10px; border:1px solid #ccbba5; background:#fff; font:inherit; }
    .full { grid-column:1 / -1; }
    .hint { font-size:13px; color:#6c5a46; margin-top:6px; }
    button { margin-top:12px; border:0; border-radius:999px; padding:12px 18px; background:var(--accent); color:white; font-weight:700; cursor:pointer; }
    .status { margin:12px 0 0; font-weight:700; color:#166534; }
    .muted { color:#6c5a46; font-size:13px; }
    code { background:#f4eadb; padding:2px 6px; border-radius:6px; }
    .logbox { height:70vh; min-height:520px; overflow:auto; padding:14px; border-radius:14px; border:1px solid #d8c7b4; background:#fffaf3; white-space:pre-wrap; font-family:Consolas, "Courier New", monospace; font-size:13px; line-height:1.45; }
    @media (max-width: 980px) { .layout { grid-template-columns:1fr; } }
    @media (max-width: 700px) { .grid { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="layout">
      <div class="card">
        <h1>Codex YT Switch</h1>
        <p>Adjust the live behavior here. Save applies to <code>config.json</code> and updates the running process immediately.</p>
        {% if saved %}
        <div class="status">Settings saved.</div>
        {% endif %}
        <form method="post">
          <div class="grid">
            <div>
              <label for="switch_strategy">Switch strategy</label>
              <select id="switch_strategy" name="switch_strategy">
                <option value="alt_tab" {% if config.switch_strategy == 'alt_tab' %}selected{% endif %}>Alt+Tab</option>
              </select>
            </div>
            <div>
              <label for="switch_back_timeout_seconds">Return timeout (seconds)</label>
              <input id="switch_back_timeout_seconds" name="switch_back_timeout_seconds" type="number" min="1" step="1" value="{{ config.switch_back_timeout_seconds }}">
            </div>
            <div>
              <label for="switch_delay_seconds">Delay after switch (seconds)</label>
              <input id="switch_delay_seconds" name="switch_delay_seconds" type="number" min="0" step="0.05" value="{{ config.switch_delay_seconds }}">
            </div>
            <div>
              <label for="poll_interval_seconds">Poll interval (seconds)</label>
              <input id="poll_interval_seconds" name="poll_interval_seconds" type="number" min="0.1" step="0.1" value="{{ config.poll_interval_seconds }}">
            </div>
            <div class="full">
              <label for="switch_to_sendkeys">Keys before switching from browser to Codex</label>
              <input id="switch_to_sendkeys" name="switch_to_sendkeys" type="text" value="{{ config.switch_to_sendkeys }}">
              <div class="hint">These keys are sent first, while the browser is still active. After that the app switches to Codex.</div>
            </div>
            <div class="full">
              <label for="switch_back_sendkeys">Keys after switching back from Codex to browser</label>
              <input id="switch_back_sendkeys" name="switch_back_sendkeys" type="text" value="{{ config.switch_back_sendkeys }}">
              <div class="hint">The app switches back to the browser first, then sends these keys there. Examples: <code>{SPACE}</code>, <code>{ENTER}</code>, <code>^l</code>.</div>
            </div>
            <div class="full">
              <label for="browser_process_names">Browser process names</label>
              <input id="browser_process_names" name="browser_process_names" type="text" value="{{ ', '.join(config.browser_process_names) }}">
            </div>
          </div>
          <button type="submit">Save settings</button>
        </form>
      </div>
      <div class="card">
        <h2>Live Logs</h2>
        <p class="muted">Readable Python status messages appear here live.</p>
        <div id="logbox" class="logbox">Loading logs...</div>
      </div>
    </div>
  </div>
  <script>
    const logbox = document.getElementById("logbox");
    let lastText = "";
    async function refreshLogs() {
      try {
        const response = await fetch("/api/console-log", { cache: "no-store" });
        const data = await response.json();
        if (typeof data.text === "string" && data.text !== lastText) {
          const shouldStick = logbox.scrollTop + logbox.clientHeight >= logbox.scrollHeight - 24;
          logbox.textContent = data.text || "No log output yet.";
          lastText = data.text;
          if (shouldStick) {
            logbox.scrollTop = logbox.scrollHeight;
          }
        }
      } catch (error) {
        logbox.textContent = "Logs could not be loaded right now.";
      }
    }
    refreshLogs();
    setInterval(refreshLogs, 1200);
  </script>
</body>
</html>
"""


def setup_logging(config: dict) -> None:
    log_path = Path(config["debug_log_path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )


def log(message: str) -> None:
    LOGGER.info(message)


def console_status(message: str) -> None:
    prefix = f"[{datetime.now().strftime('%H:%M:%S')}] "
    lower = message.lower()
    human_message = None

    if "codex yt switch is starting." in lower:
        human_message = "Codex YT Switch is starting."
    elif "starting settings web server at" in lower:
        human_message = message.replace("Starting settings web server at ", "Settings page started at: ")
    elif "watching codex logs at:" in lower:
        human_message = message.replace("Watching Codex logs at: ", "Watching Codex logs at: ")
    elif "applied new config:" in lower:
        human_message = "Settings were applied."
    elif "switched away from browser using strategy=" in lower:
        human_message = "Switched to Codex: a new Codex Windows notification was detected."
    elif "switched back after user submitted a new codex message" in lower:
        human_message = "Switched back to the browser: your new input was sent to Codex."
    elif "ignoring switch-back event" in lower and "no pending return is active" in lower:
        human_message = "A new Codex request was detected, but no browser return was pending."
    elif "did not switch for trigger_id=" in lower and "foreground is not a configured browser" in lower:
        human_message = "Did not switch to Codex because the foreground window was not a configured browser."
    elif "ignoring switch-back event because codex is not the foreground app." in lower:
        human_message = "Did not switch back because Codex was not the foreground app when the message was sent."
    elif "no new codex submission arrived in time; clearing pending browser return." in lower:
        human_message = "Pending browser return expired because no new Codex submission arrived in time."
    elif "failed to switch away from browser" in lower:
        human_message = "Failed to switch to Codex."
    elif "failed to switch back after switch-back event" in lower:
        human_message = "Failed to switch back to the browser."
    elif "sent extra keys for switch_to_codex_before_switch" in lower:
        human_message = "Extra keys were sent while the browser was still active."
    elif "sent extra keys for switch_back" in lower:
        human_message = "Extra keys were sent after switching back to the browser."

    if not human_message:
        return

    line = prefix + human_message
    print(line, flush=True)
    console_log_path = ROOT / "console_status.log"
    with console_log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def emit(message: str) -> None:
    log(message)
    console_status(message)


def starts_with_any(message: str, prefixes: list[str]) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False
    return any(text.startswith(prefix) for prefix in prefixes)


def ensure_config() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        return DEFAULT_CONFIG.copy()
    loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    merged = DEFAULT_CONFIG.copy()
    merged.update(loaded)
    return merged


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def read_console_log_tail(max_lines: int = 250) -> str:
    console_log_path = ROOT / "console_status.log"
    if not console_log_path.exists():
        return ""
    lines = console_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def process_name_for_hwnd(hwnd: int) -> str:
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return psutil.Process(pid).name().lower()
    except Exception:
        return ""


def window_title(hwnd: int) -> str:
    try:
        return win32gui.GetWindowText(hwnd)
    except Exception:
        return ""


def get_foreground_window() -> int:
    return win32gui.GetForegroundWindow()


def is_browser_window(hwnd: int, browser_names: set[str]) -> bool:
    return process_name_for_hwnd(hwnd) in browser_names


def send_alt_tab() -> bool:
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shell.SendKeys("%{TAB}")
        emit("Sent Alt+Tab to Windows.")
        return True
    except Exception as exc:
        emit(f"send_alt_tab failed: {exc!r}")
        return False


def send_configured_keys(keys: str, context: str) -> bool:
    if not keys:
        return True
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shell.SendKeys(keys)
        emit(f"Sent extra keys for {context}: {keys!r}")
        return True
    except Exception as exc:
        emit(f"Failed to send extra keys for {context} {keys!r}: {exc!r}")
        return False


def virtual_key_for_digit(key: str) -> Optional[int]:
    if key and len(key) == 1 and key.isdigit():
        return ord(key)
    return None


def is_virtual_key_pressed(vk_code: int) -> bool:
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000)
    except Exception:
        return False


def extract_notification_text_lines(user_notification) -> list[str]:
    visual = user_notification.notification.visual
    if visual is None:
        return []

    binding = visual.get_binding("ToastGeneric")
    if binding is None:
        return []

    return [element.text.strip() for element in binding.get_text_elements() if element.text.strip()]


class WindowsNotificationWatcher:
    def __init__(self, app_substrings: list[str]) -> None:
        self.app_substrings = [part.lower() for part in app_substrings if part.strip()]
        self.listener = None
        self.is_supported = UserNotificationListener is not None
        self.has_access = False
        self.seen_notification_ids: set[int] = set()
        self._initialize()

    async def _read_notifications_async(self):
        return await self.listener.get_notifications_async(NotificationKinds.TOAST)

    def _initialize(self) -> None:
        if not self.is_supported:
            emit("Windows notification listener is unavailable because WinRT packages are missing.")
            return

        try:
            self.listener = UserNotificationListener.current
            status = self.listener.get_access_status()
            if status != UserNotificationListenerAccessStatus.ALLOWED:
                emit("Windows notification access is not allowed yet; requesting permission.")
                status = asyncio.run(self.listener.request_access_async())
            if status != UserNotificationListenerAccessStatus.ALLOWED:
                emit(f"Windows notification access is unavailable; status={status.name}")
                return

            notifications = asyncio.run(self._read_notifications_async())
            self.seen_notification_ids = {int(notification.id) for notification in notifications}
            self.has_access = True
            emit(
                "Windows notification watcher initialized successfully; "
                f"baseline_notifications={len(self.seen_notification_ids)}"
            )
        except Exception as exc:
            emit(f"Failed to initialize Windows notification watcher: {exc!r}")

    def _matches_codex_app(self, app_name: str) -> bool:
        lowered = (app_name or "").strip().lower()
        if not lowered:
            return False
        return any(part in lowered for part in self.app_substrings)

    def pop_events(self) -> list[tuple[str, int, str]]:
        if not self.has_access or not self.listener:
            return []

        try:
            notifications = asyncio.run(self._read_notifications_async())
        except Exception as exc:
            emit(f"Failed to poll Windows notifications: {exc!r}")
            return []

        current_ids: set[int] = set()
        events: list[tuple[str, int, str]] = []
        for notification in notifications:
            notification_id = int(notification.id)
            current_ids.add(notification_id)
            if notification_id in self.seen_notification_ids:
                continue

            try:
                app_name = notification.app_info.display_info.display_name
            except Exception:
                app_name = ""

            if not self._matches_codex_app(app_name):
                continue

            lines = extract_notification_text_lines(notification)
            title = lines[0] if lines else ""
            body = "\n".join(lines[1:]) if len(lines) > 1 else ""
            emit(
                f"Matched Codex Windows notification id={notification_id} "
                f"app_name={app_name!r} title={title!r}"
            )
            events.append(
                (
                    "switch_to_codex",
                    notification_id,
                    f"app={app_name} title={title} body={body}",
                )
            )

        self.seen_notification_ids = current_ids
        return events


class CodexLogWatcher:
    def __init__(
        self,
        db_path: Path,
        switch_back_substrings: list[str],
    ) -> None:
        self.db_path = db_path
        self.switch_back_substrings = [part.lower() for part in switch_back_substrings]
        self.body_column = "message"
        self.last_seen_id = self._read_last_id()

    def _connect(self):
        return sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=1)

    def _detect_body_column(self) -> str:
        try:
            with self._connect() as conn:
                rows = conn.execute("pragma table_info(logs)").fetchall()
        except sqlite3.Error:
            return "message"

        columns = {row[1] for row in rows}
        if "feedback_log_body" in columns:
            return "feedback_log_body"
        if "message" in columns:
            return "message"
        return "message"

    def _read_last_id(self) -> int:
        if not self.db_path.exists():
            emit(f"Log database does not exist yet: {self.db_path}")
            return 0
        try:
            with self._connect() as conn:
                self.body_column = self._detect_body_column()
                row = conn.execute("select coalesce(max(id), 0) from logs").fetchone()
            emit(
                f"Watcher initialized db={self.db_path} body_column={self.body_column} last_seen_id={int(row[0] or 0)}"
            )
            return int(row[0] or 0)
        except sqlite3.Error as exc:
            emit(f"Failed to read initial last id from {self.db_path}: {exc!r}")
            return 0

    def pop_events(self) -> list[tuple[str, int, str]]:
        if not self.db_path.exists():
            return []
        try:
            with self._connect() as conn:
                self.body_column = self._detect_body_column()
                rows = conn.execute(
                    f"select id, {self.body_column} from logs where id > ? order by id asc",
                    (self.last_seen_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            emit(f"Failed to poll Codex logs: {exc!r}")
            return []

        events: list[tuple[str, int, str]] = []
        for row_id, message in rows:
            self.last_seen_id = max(self.last_seen_id, int(row_id))
            if starts_with_any(message or "", self.switch_back_substrings):
                snippet = (message or "").replace("\n", " ")[:180]
                emit(f"Matched switch-back event row_id={row_id} body_column={self.body_column} snippet={snippet!r}")
                events.append(("switch_back", int(row_id), message or ""))
        return events


class SwitchController:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.browser_names = {name.lower() for name in config["browser_process_names"]}
        self.codex_names = {name.lower() for name in config["codex_process_names"]}
        self.switch_strategy = config.get("switch_strategy", "alt_tab").lower()
        self.switch_back_hotkeys = self._parse_switch_back_hotkeys(config)
        self.pending_return: Optional[PendingReturn] = None
        self.last_trigger_at = 0.0
        self.last_trigger_id = 0
        self._pressed_hotkeys: set[str] = set()
        self.lock = threading.Lock()

    def _parse_switch_back_hotkeys(self, config: dict) -> set[str]:
        raw_keys = config.get("switch_back_hotkeys", ["1", "2"])
        parsed: set[str] = set()
        for key in raw_keys:
            normalized = str(key).strip()
            if virtual_key_for_digit(normalized) is not None:
                parsed.add(normalized)
        return parsed

    def apply_config(self, config: dict) -> None:
        with self.lock:
            self.config = config
            self.browser_names = {name.lower() for name in config["browser_process_names"]}
            self.codex_names = {name.lower() for name in config["codex_process_names"]}
            self.switch_strategy = config.get("switch_strategy", "alt_tab").lower()
            self.switch_back_hotkeys = self._parse_switch_back_hotkeys(config)
        emit(
            f"Applied new config: switch_strategy={self.switch_strategy} "
            f"switch_to_sendkeys={config.get('switch_to_sendkeys', '')!r} "
            f"switch_back_sendkeys={config.get('switch_back_sendkeys', '')!r}"
        )

    def handle_switch_to_codex(self, trigger_id: int, message: str) -> None:
        with self.lock:
            if self.pending_return:
                self.last_trigger_id = trigger_id
                emit(
                    f"Ignoring trigger_id={trigger_id} because a browser return is already pending "
                    f"from an earlier Codex switch."
                )
                return
            if trigger_id <= self.last_trigger_id:
                emit(f"Ignoring trigger_id={trigger_id} because it is not newer than last_trigger_id={self.last_trigger_id}")
                return
            now = time.time()
            if now - self.last_trigger_at < float(self.config["dedupe_window_seconds"]):
                self.last_trigger_id = trigger_id
                emit(
                    f"Ignoring trigger_id={trigger_id} due to dedupe window; "
                    f"seconds_since_last={now - self.last_trigger_at:.2f}"
                )
                return
            browser_hwnd = get_foreground_window()
            browser_process = process_name_for_hwnd(browser_hwnd) if browser_hwnd else ""
            browser_title = window_title(browser_hwnd) if browser_hwnd else ""
            emit(
                f"Handling trigger_id={trigger_id}; foreground_hwnd={browser_hwnd} "
                f"foreground_process={browser_process} foreground_title={browser_title!r}"
            )
            if not browser_hwnd or not is_browser_window(browser_hwnd, self.browser_names):
                self.last_trigger_id = trigger_id
                emit(f"Did not switch for trigger_id={trigger_id} because foreground is not a configured browser.")
                return

            time.sleep(float(self.config.get("switch_delay_seconds", 0.15)))
            send_configured_keys(self.config.get("switch_to_sendkeys", ""), "switch_to_codex_before_switch")
            activated = send_alt_tab()

            if not activated:
                self.last_trigger_id = trigger_id
                emit(f"Failed to switch away from browser for trigger_id={trigger_id}")
                return
            self.pending_return = PendingReturn(browser_hwnd=browser_hwnd, activated_at=now)
            self._pressed_hotkeys.clear()
            self.last_trigger_at = now
            self.last_trigger_id = trigger_id
            emit(
                f"Switched away from browser using strategy={self.switch_strategy} for trigger_id={trigger_id}; "
                f"saved_browser_hwnd={browser_hwnd} saved_browser_process={browser_process} "
                f"source_message={message!r}"
            )

    def handle_switch_back(self, trigger_id: int, message: str) -> None:
        with self.lock:
            if not self.pending_return:
                emit(f"Ignoring switch-back event row_id={trigger_id} because no pending return is active.")
                return
            foreground = get_foreground_window()
            foreground_process = process_name_for_hwnd(foreground)
            emit(f"Handling switch-back event row_id={trigger_id}; foreground_process={foreground_process}")
            if foreground_process not in self.codex_names:
                emit("Ignoring switch-back event because Codex is not the foreground app.")
                return
            browser_hwnd = self.pending_return.browser_hwnd
            self.pending_return = None
            self._pressed_hotkeys.clear()

        self._perform_switch_back(browser_hwnd, "user submitted a new Codex message")

    def check_switch_back_hotkeys(self) -> None:
        with self.lock:
            if not self.pending_return or not self.switch_back_hotkeys:
                self._pressed_hotkeys.clear()
                return

            foreground = get_foreground_window()
            foreground_process = process_name_for_hwnd(foreground)
            if foreground_process not in self.codex_names:
                self._pressed_hotkeys.clear()
                return

            triggered_key = None
            currently_pressed: set[str] = set()
            for key in self.switch_back_hotkeys:
                vk_code = virtual_key_for_digit(key)
                if vk_code is None:
                    continue
                if is_virtual_key_pressed(vk_code):
                    currently_pressed.add(key)
                    if key not in self._pressed_hotkeys and triggered_key is None:
                        triggered_key = key

            self._pressed_hotkeys = currently_pressed
            if not triggered_key:
                return

            browser_hwnd = self.pending_return.browser_hwnd
            self.pending_return = None
            self._pressed_hotkeys.clear()

        emit(f"Detected switch-back hotkey {triggered_key!r} while Codex was focused.")
        self._perform_switch_back(browser_hwnd, f"hotkey {triggered_key}")

    def _perform_switch_back(self, browser_hwnd: int, reason: str) -> None:
        time.sleep(0.15)
        if send_alt_tab():
            time.sleep(float(self.config.get("switch_delay_seconds", 0.15)))
            send_configured_keys(self.config.get("switch_back_sendkeys", ""), "switch_back")
            emit(
                f"Switched back after {reason} using strategy={self.switch_strategy}; "
                f"previous_browser_hwnd={browser_hwnd}"
            )
        else:
            emit(f"Failed to switch back after {reason}; previous_browser_hwnd={browser_hwnd}")

    def expire_pending(self) -> None:
        with self.lock:
            if not self.pending_return:
                return
            timeout = float(self.config["switch_back_timeout_seconds"])
            if time.time() - self.pending_return.activated_at <= timeout:
                return
            emit("No new Codex submission arrived in time; clearing pending browser return.")
            self.pending_return = None
            self._pressed_hotkeys.clear()


class RuntimeState:
    def __init__(self, config: dict, controller: SwitchController) -> None:
        self.lock = threading.Lock()
        self.config = config
        self.controller = controller

    def get_config(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.config))

    def update_from_form(self, form) -> None:
        with self.lock:
            self.config["switch_strategy"] = form.get("switch_strategy", "alt_tab").strip() or "alt_tab"
            self.config["switch_back_timeout_seconds"] = int(float(form.get("switch_back_timeout_seconds", 120)))
            self.config["switch_delay_seconds"] = float(form.get("switch_delay_seconds", 0.15))
            self.config["poll_interval_seconds"] = float(form.get("poll_interval_seconds", 0.8))
            self.config["switch_to_sendkeys"] = form.get("switch_to_sendkeys", "").strip()
            self.config["switch_back_sendkeys"] = form.get("switch_back_sendkeys", "").strip()
            browsers = form.get("browser_process_names", "")
            self.config["browser_process_names"] = [part.strip() for part in browsers.split(",") if part.strip()]
            save_config(self.config)
            self.controller.apply_config(self.config)


def create_web_routes(state: RuntimeState) -> None:
    @WEB_APP.route("/", methods=["GET", "POST"])
    def index():
        saved = False
        if request.method == "POST":
            state.update_from_form(request.form)
            saved = True
        config = state.get_config()
        return render_template_string(SETTINGS_TEMPLATE, config=config, saved=saved)

    @WEB_APP.route("/health")
    def health():
        return {"ok": True}

    @WEB_APP.route("/api/console-log")
    def api_console_log():
        return {"text": read_console_log_tail()}


def start_web_server(state: RuntimeState) -> None:
    create_web_routes(state)

    def run_server():
        config = state.get_config()
        host = config.get("web_host", "127.0.0.1")
        port = int(config.get("web_port", 5057))
        emit(f"Starting settings web server at http://{host}:{port}")
        WEB_APP.run(host=host, port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()


def main() -> None:
    config = ensure_config()
    setup_logging(config)
    notification_watcher = WindowsNotificationWatcher(config.get("codex_notification_app_substrings", ["codex"]))
    watcher = CodexLogWatcher(
        Path(config["codex_log_db_path"]),
        config["switch_back_substrings"],
    )
    controller = SwitchController(config)
    runtime_state = RuntimeState(config, controller)
    last_heartbeat = 0.0

    emit("Codex YT Switch is starting.")
    emit(f"Watching Codex logs at: {config['codex_log_db_path']}")
    emit(
        "Watching Windows notifications for Codex app names: "
        f"{config.get('codex_notification_app_substrings', ['codex'])}"
    )
    emit(f"Configured browsers={sorted(controller.browser_names)} codex_processes={sorted(controller.codex_names)}")
    emit("Windows-notification-based switch-to-Codex and log-based switch-back detection initialized successfully.")
    start_web_server(runtime_state)

    def monitor_loop():
        nonlocal last_heartbeat
        while True:
            try:
                events = notification_watcher.pop_events() + watcher.pop_events()
                for event_type, row_id, message in events:
                    if event_type == "switch_to_codex":
                        controller.handle_switch_to_codex(row_id, message)
                    elif event_type == "switch_back":
                        controller.handle_switch_back(row_id, message)
                # Optional fallback: allow immediate switch-back via keyboard while Codex is focused.
                # Disabled for now, but kept in the code in case we want to re-enable it later.
                # controller.check_switch_back_hotkeys()
                controller.expire_pending()
                if time.time() - last_heartbeat >= float(config["heartbeat_interval_seconds"]):
                    fg = get_foreground_window()
                    emit(
                        f"Heartbeat foreground_hwnd={fg} foreground_process={process_name_for_hwnd(fg)} "
                        f"foreground_title={window_title(fg)!r} last_seen_id={watcher.last_seen_id} "
                        f"pending_return={bool(controller.pending_return)}"
                    )
                    last_heartbeat = time.time()
                time.sleep(float(config["poll_interval_seconds"]))
            except Exception as exc:
                emit(f"Monitor loop crashed temporarily with error: {exc!r}")
                time.sleep(1.0)

    emit("Entering main monitor loop.")
    monitor_loop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            setup_logging(ensure_config())
            emit(f"Fatal startup error: {exc!r}")
        finally:
            raise
