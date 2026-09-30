import pytest

from pricecharter.consoles import REGIONS, all_consoles, by_slug, resolve


def test_registry_has_16_platforms_in_3_regions():
    consoles = all_consoles()
    assert len(consoles) == 48
    assert {c.region for c in consoles} == set(REGIONS) == {"ntsc-u", "pal", "ntsc-j"}
    assert len({c.slug for c in consoles}) == 48


@pytest.mark.parametrize(
    "slug, platform, region",
    [
        ("nes", "nes", "ntsc-u"),
        ("pal-nes", "nes", "pal"),
        ("famicom", "nes", "ntsc-j"),
        ("super-famicom", "snes", "ntsc-j"),
        ("jp-playstation-2", "ps2", "ntsc-j"),
        ("pal-xbox-360", "xbox360", "pal"),
        ("wii-u", "wiiu", "ntsc-u"),
    ],
)
def test_by_slug(slug, platform, region):
    c = by_slug(slug)
    assert (c.platform, c.region) == (platform, region)


def test_by_slug_unknown():
    assert by_slug("not-a-console") is None


def test_resolve_platform_expands_regions():
    assert [c.slug for c in resolve(["nes"])] == ["nes", "pal-nes", "famicom"]
    assert [c.slug for c in resolve(["snes", "ps2"], ["ntsc-j"])] == ["super-famicom", "jp-playstation-2"]


def test_resolve_explicit_slug_ignores_region_filter():
    assert [c.slug for c in resolve(["pal-wii"], ["ntsc-u"])] == ["pal-wii"]


def test_resolve_default_is_everything():
    assert len(resolve(None)) == 48


def test_resolve_unknown_raises():
    with pytest.raises(ValueError):
        resolve(["dreamcast"])


def test_cli_region_flag():
    from pricecharter.cli import parse_args

    assert parse_args(["list", "-c", "nes", "-r", "pal", "ntsc-j"]).consoles == ["pal-nes", "famicom"]
    assert len(parse_args(["all"]).consoles) == 48


def test_cli_rejects_unknown_console():
    from pricecharter.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["list", "-c", "dreamcast"])
