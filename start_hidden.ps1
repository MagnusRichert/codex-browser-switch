$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "python"
$script = Join-Path $root "codex_yt_switch.py"
$stdout = Join-Path $root "codex_yt_switch.stdout.log"
$stderr = Join-Path $root "codex_yt_switch.stderr.log"

Start-Process -WindowStyle Hidden -FilePath $python -ArgumentList @($script) -WorkingDirectory $root -RedirectStandardOutput $stdout -RedirectStandardError $stderr
