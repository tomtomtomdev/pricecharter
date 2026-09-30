"""Console registry: each platform exists once per region, each with its own PriceCharting slug."""

from dataclasses import dataclass

REGIONS = ("ntsc-u", "pal", "ntsc-j")

# platform alias -> NTSC-U slug; PAL is "pal-<slug>", NTSC-J is "jp-<slug>" unless overridden
_PLATFORMS = {
    "nes": "nes",
    "snes": "super-nintendo",
    "gba": "gameboy-advance",
    "ds": "nintendo-ds",
    "3ds": "nintendo-3ds",
    "gamecube": "gamecube",
    "wii": "wii",
    "wiiu": "wii-u",
    "ps1": "playstation",
    "ps2": "playstation-2",
    "psp": "psp",
    "vita": "playstation-vita",
    "ps3": "playstation-3",
    "switch": "nintendo-switch",
    "xbox": "xbox",
    "xbox360": "xbox-360",
}
_JP_OVERRIDES = {"nes": "famicom", "snes": "super-famicom"}


@dataclass(frozen=True)
class Console:
    slug: str
    platform: str
    region: str


def _build() -> list[Console]:
    out = []
    for platform, us in _PLATFORMS.items():
        out.append(Console(us, platform, "ntsc-u"))
        out.append(Console(f"pal-{us}", platform, "pal"))
        out.append(Console(_JP_OVERRIDES.get(platform, f"jp-{us}"), platform, "ntsc-j"))
    return out


_ALL = _build()
_BY_SLUG = {c.slug: c for c in _ALL}


def all_consoles() -> list[Console]:
    return list(_ALL)


def by_slug(slug: str) -> Console | None:
    return _BY_SLUG.get(slug)


def platforms() -> list[str]:
    return list(_PLATFORMS)


def resolve(names: list[str] | None, regions: list[str] | None = None) -> list[Console]:
    """Platform aliases expand to the chosen regions; explicit slugs are taken as-is."""
    regions = list(regions or REGIONS)
    if not names:
        names = platforms()
    out: list[Console] = []
    for name in names:
        if name in _PLATFORMS:
            out += [c for c in _ALL if c.platform == name and c.region in regions]
        elif name in _BY_SLUG:
            out.append(_BY_SLUG[name])
        else:
            raise ValueError(f"unknown console {name!r}; platforms: {', '.join(_PLATFORMS)}")
    return list(dict.fromkeys(out))
