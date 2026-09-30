import plistlib
import subprocess
from pathlib import Path

from pricecharter.schedule import LABEL, build_plist, guard_command

PROJECT = Path("/Users/me/pricecharter")


def _plist(**kw):
    return plistlib.loads(build_plist(PROJECT, **kw))


def test_weekend_1am_start():
    p = _plist()
    assert p["Label"] == LABEL
    assert p["StartCalendarInterval"] == [
        {"Weekday": 6, "Hour": 1, "Minute": 0},  # Saturday
        {"Weekday": 0, "Hour": 1, "Minute": 0},  # Sunday
    ]


def test_runs_crawler_until_23():
    p = _plist()
    assert p["ProgramArguments"][:2] == ["/bin/bash", "-c"]
    cmd = p["ProgramArguments"][2]
    assert f"exec {PROJECT}/run.sh all --until 23:00" in cmd
    assert p["WorkingDirectory"] == str(PROJECT)
    assert p["StandardOutPath"] == str(PROJECT / "logs" / "crawl.log")
    assert "/opt/homebrew/bin" in p["EnvironmentVariables"]["PATH"]
    assert p.get("RunAtLoad", False) is False


def test_custom_window():
    p = _plist(start="02:30", until="22:00")
    assert p["StartCalendarInterval"][0] == {"Weekday": 6, "Hour": 2, "Minute": 30}
    assert "--until 22:00" in p["ProgramArguments"][2]


def _guard_passes(day_of_week: int) -> bool:
    """Run the guard with `date +%u` stubbed to a given ISO weekday (1=Mon .. 7=Sun)."""
    guard = guard_command().replace("$(date +%u)", str(day_of_week))
    return subprocess.run(["/bin/bash", "-c", guard], check=False).returncode == 0


def test_guard_only_allows_weekend():
    assert [d for d in range(1, 8) if _guard_passes(d)] == [6, 7]
