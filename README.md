# Codex Browser Switch

Codex Browser Switch is a small Windows helper that automatically moves you between your browser and the Codex desktop app at the right moments.

The goal is simple: when Codex finishes and shows a Windows notification, the app can bring Codex to the foreground for you. When you send a new message, command approval, or other follow-up back to Codex, it can switch you back to the browser again. That way you do not have to keep manually alt-tabbing between both windows during a workflow.

In short, it does this:

1. Watches Windows toast notifications and reacts when Codex posts a new Windows notification.
2. If your active window is a browser, it can send optional browser-side keys and then perform a normal Windows `Alt+Tab` to bring Codex forward.
3. Once you send a new message or approval back to Codex, it detects the new Codex request in the logs.
4. Right after that, it can switch back to the browser and optionally send browser-side keys there.

This project also includes a small local settings page so you can adjust timing, browser process names, SendKeys behavior, the watched Codex log database path, and whether the automation is currently enabled.

## Interface Preview

![Codex Browser Switch Flask interface](./codex%20switch.png)

## Files

- `codex_yt_switch.py`: the background app
- `codex_yt_switch_launcher.pyw`: double-click launcher without a PowerShell window
- `config.json`: tweakable process names and trigger rules
- `codex_yt_switch.log`: file log with startup, trigger, and switch behavior
- `start_hidden.ps1`: optional hidden launcher, if you want it later

## Run it

Install dependencies first:

```powershell
python -m pip install -r .\requirements.txt
```

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
- The watched Codex log database path can be edited in the UI, so other users can override the default user-specific path.
- You can configure SendKeys sequences for two separate moments: before switching from browser to Codex, and after switching back from Codex to browser.
- The browser is restored when Codex logs a new `response.created` event, which means your new input was sent.
- The Windows notification listener needs user permission on Windows the first time it is used.
