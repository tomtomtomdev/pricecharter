"""Weekend crawl schedule as a macOS launchd LaunchAgent.

A LaunchAgent runs inside the logged-in GUI session, which headed Chrome needs.
If the Mac is asleep at start time, launchd runs the job on wake; the weekday guard
keeps a late wake on Monday from starting a crawl.

    python -m pricecharter.schedule install|uninstall|status|print
"""

import argparse
import os
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path

from .window import deadline_from

LABEL = "dev.tomtomtomdev.pricecharter"
AGENT = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
SATURDAY, SUNDAY = 6, 0  # launchd Weekday numbering
PATH = f"{Path.home()}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def guard_command() -> str:
    """Succeeds only on Saturday (6) or Sunday (7), ISO weekday numbering."""
    return '[ "$(date +%u)" -ge 6 ]'


def _hhmm(value: str) -> tuple[int, int]:
    d = deadline_from(value)  # validates HH:MM
    return d.hour, d.minute


def build_plist(project: Path, start: str = "01:00", until: str = "23:00") -> bytes:
    hour, minute = _hhmm(start)
    _hhmm(until)
    logs = project / "logs"
    run = shlex.quote(str(project / "run.sh"))
    cmd = (
        f'echo "=== $(date) ==="; '
        f'{guard_command()} || {{ echo "not a weekend day, skipping"; exit 0; }}; '
        f"exec {run} all --until {until}"
    )
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": ["/bin/bash", "-c", cmd],
        "WorkingDirectory": str(project),
        "StartCalendarInterval": [
            {"Weekday": SATURDAY, "Hour": hour, "Minute": minute},
            {"Weekday": SUNDAY, "Hour": hour, "Minute": minute},
        ],
        "EnvironmentVariables": {"PATH": PATH},
        "StandardOutPath": str(logs / "crawl.log"),
        "StandardErrorPath": str(logs / "crawl.log"),
        "ProcessType": "Background",
    })


def _launchctl(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=check)


def install(project: Path, start: str, until: str) -> None:
    (project / "logs").mkdir(exist_ok=True)
    AGENT.parent.mkdir(parents=True, exist_ok=True)
    AGENT.write_bytes(build_plist(project, start, until))
    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", domain, str(AGENT))
    _launchctl("bootstrap", domain, str(AGENT), check=True)
    print(f"installed {AGENT}\nweekends {start}–{until}; log: {project / 'logs' / 'crawl.log'}")
    print("tip: to wake the Mac for it, run  sudo pmset repeat wakeorpoweron SU 00:55:00")


def uninstall() -> None:
    _launchctl("bootout", f"gui/{os.getuid()}", str(AGENT))
    AGENT.unlink(missing_ok=True)
    print(f"removed {LABEL}")


def status(project: Path) -> None:
    r = _launchctl("print", f"gui/{os.getuid()}/{LABEL}")
    if r.returncode:
        print("not installed")
        return
    keep = ("state =", "last exit code", "runs =", "pid =")
    print("\n".join(line.strip() for line in r.stdout.splitlines() if line.strip().startswith(keep)))
    log = project / "logs" / "crawl.log"
    if log.exists():
        print(f"--- {log} (last 10 lines)")
        print("\n".join(log.read_text(errors="replace").splitlines()[-10:]))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="schedule")
    ap.add_argument("action", choices=["install", "uninstall", "status", "print"])
    ap.add_argument("--start", default="01:00")
    ap.add_argument("--until", default="23:00")
    ap.add_argument("--project", type=Path, default=Path(__file__).resolve().parent.parent)
    a = ap.parse_args(argv)
    if a.action == "install":
        install(a.project, a.start, a.until)
    elif a.action == "uninstall":
        uninstall()
    elif a.action == "status":
        status(a.project)
    else:
        sys.stdout.write(build_plist(a.project, a.start, a.until).decode())


if __name__ == "__main__":
    main()
