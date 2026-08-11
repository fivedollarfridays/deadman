"""What the public board may say about a surface.

``GET /`` is deployed ``--allow-unauthenticated`` and its URL is published, so
everything this module returns is world-readable. Before DM2 that was a
narrower question than it is now: the rows came only from probes running inside
this process, and the worst they carried was a local path. Ingest changed the
shape of the risk — a row now arrives from a collector on Kevin's Mac or the
rig carrying that machine's absolute paths, the collector's id, and our own
arrival times. Publishing those verbatim hands a stranger a map of a private
estate, so the board publishes a projection rather than the row.

**The gate is on the shape of a value, not on a list of blessed key names.**
A key allowlist is the obvious design and it fails open exactly where it
matters: the moment a new probe adds a key nobody remembered to classify, that
key publishes. Probes are expected to keep arriving, so the rule is instead
that scalars and short non-path strings publish and everything else does not.
A new probe's numeric detail keeps working with no edit here; a new probe's
path does not leak.

**Withheld keys are named, never silently dropped.** The names are not
sensitive, and a board that quietly omits fields teaches its reader that what
they see is everything — the same false completeness this project objects to
everywhere else. A reader who needs a withheld value knows it exists and can
go and read the store directly.
"""

from __future__ import annotations

from deadman.ingest.arrival import COLLECTOR_ID, RECEIVED_AT, REPORTED_METHOD, WIRE_ROW_ID

#: Detail keys the board never publishes. They describe *our* topology rather
#: than the surface's condition: who reported it, when we heard it, the row's
#: dedupe identity, and the pre-downgrade claim. A reader learns nothing about
#: whether the estate is healthy from any of them.
WITHHELD_DETAIL_KEYS = frozenset({COLLECTOR_ID, RECEIVED_AT, REPORTED_METHOD, WIRE_ROW_ID})

#: Longest string value the board will publish from ``detail``.
MAX_PUBLISHED_TEXT = 200

_PATH_PREFIXES = ("/", "~", "\\")
_PATH_MARKERS = ("/Users/", "/home/", "C:\\")


def publishable(value: object) -> bool:
    """Whether a ``detail`` value is safe for an unauthenticated reader."""
    if value is None or isinstance(value, bool) or isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return (
            len(value) <= MAX_PUBLISHED_TEXT
            and "/" not in value
            and "\\" not in value
            and not value.startswith("~")
        )
    return False


def public_detail(detail: dict[str, object]) -> dict[str, object]:
    """``detail`` as the public board may show it, with omissions named."""
    kept = {
        key: value
        for key, value in detail.items()
        if key not in WITHHELD_DETAIL_KEYS and publishable(value)
    }
    withheld = sorted(key for key in detail if key not in kept)
    if withheld:
        kept["withheld"] = withheld
    return kept


def public_source(source: str) -> str:
    """``source`` with a filesystem path reduced to its final component.

    ``source`` names the instrument, which is worth publishing; the absolute
    path to it maps a private machine, which is not. Only genuinely path-shaped
    values are reduced — an instrument name may legitimately contain a slash
    (``statvfs:/``, ``shutil.disk_usage('/')``), and reducing those would strip
    the board of the very thing this field exists to say.
    """
    if not (source.startswith(_PATH_PREFIXES) or any(m in source for m in _PATH_MARKERS)):
        return source
    return source.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or "(path withheld)"
