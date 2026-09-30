import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(*args):
    env = {**os.environ, "PRICECHARTER_CHROME": "/nonexistent/Google Chrome"}
    return subprocess.run(["bash", str(ROOT / "run.sh"), *args], capture_output=True, text=True, env=env, timeout=120)


def test_crawl_needs_chrome():
    r = _run("list", "--help")
    assert r.returncode == 1 and "Google Chrome is required" in r.stderr


def test_serve_and_analyze_skip_chrome_check():
    for stage in ("serve", "analyze"):
        r = _run(stage, "--help")
        assert r.returncode == 0, r.stderr
        assert "usage: pricecharter" in r.stdout
