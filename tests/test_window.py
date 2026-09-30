import asyncio
from datetime import datetime, timedelta

import pytest

from pricecharter.throttle import DeadlineReached, Throttle
from pricecharter.window import deadline_from


def test_deadline_later_same_day():
    now = datetime(2026, 10, 3, 1, 0)  # Saturday 01:00
    assert deadline_from("23:00", now) == datetime(2026, 10, 3, 23, 0)


def test_deadline_already_passed_rolls_to_tomorrow():
    now = datetime(2026, 10, 3, 23, 30)
    assert deadline_from("01:00", now) == datetime(2026, 10, 4, 1, 0)


@pytest.mark.parametrize("bad", ["25:00", "7pm", "12:60", ""])
def test_deadline_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        deadline_from(bad, datetime(2026, 10, 3))


def test_throttle_raises_after_deadline():
    t = Throttle(0.0, deadline=datetime.now() - timedelta(seconds=1))
    with pytest.raises(DeadlineReached):
        asyncio.run(t.wait())


def test_throttle_without_deadline_runs():
    asyncio.run(Throttle(0.0).wait())


def test_cli_until_sets_deadline():
    from pricecharter.cli import parse_args

    assert parse_args(["all", "--until", "23:00"]).deadline.strftime("%H:%M") == "23:00"
    assert parse_args(["all"]).deadline is None
    with pytest.raises(SystemExit):
        parse_args(["all", "--until", "late"])
