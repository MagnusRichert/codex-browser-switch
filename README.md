# Codex YT Switch

This is a small Windows background helper for your Codex workflow.

It does this:

1. Watches Windows toast notifications and reacts when Codex posts a new Windows notification.
2. If your active window is a browser, it first sends any configured browser-side keys and then sends a normal Windows `Alt+Tab` to jump back to Codex.
3. Once you send a new message or approval back to Codex, it detects the new Codex request in the logs.
4. While Codex is focused, pressing `1` or `2` can also trigger the immediate jump back to the browser.
5. After either return trigger, it sends `Alt+Tab` again to jump back to the browser and only then sends any configured browser-side return keys.

## Files

- `codex_yt_switch.py`: the background app
- `codex_yt_switch_launcher.pyw`: double-click launcher without a PowerShell window
- `config.json`: tweakable process names and trigger rules
- `codex_yt_switch.log`: file log with startup, trigger, and switch behavior
- `start_hidden.ps1`: optional hidden launcher, if you want it later

## Run it

Primary way:

- Double-click [codex_yt_switch_launcher.pyw](C:\Users\Magnus\Documents\Studium\Code\openai-stuff\codex-yt-switch\codex_yt_switch_launcher.pyw) to run it without a PowerShell window.
- Or run [codex_yt_switch.py](C:\Users\Magnus\Documents\Studium\Code\openai-stuff\codex-yt-switch\codex_yt_switch.py) yourself if you want to see live `print` output in a console.

From PowerShell in this folder:

```powershell
python .\codex_yt_switch.py
```

Optional hidden start:

```powershell
.\start_hidden.ps1
```

## Notes

- Detection is based on `C:\Users\Magnus\.codex\logs_1.sqlite`.
- The switch to Codex is now triggered by a new Windows notification from the Codex app, not by `response.completed` in the Codex logs.
- Window switching now uses ordinary Windows `Alt+Tab` behavior instead of directly forcing a Codex window handle to the foreground.
- Settings UI runs locally at `http://127.0.0.1:5057`.
- The settings page includes a visible On/Off toggle that enables or disables automatic switching without stopping the app.
- You can configure SendKeys sequences for two separate moments: before switching from browser to Codex, and after switching back from Codex to browser.
- The browser is restored when Codex logs a new `response.created` event, which means your new input was sent.
- The browser is also restored immediately if Codex is focused and you press `1` or `2` while a browser return is pending.
- The Windows notification listener needs user permission on Windows the first time it is used.
