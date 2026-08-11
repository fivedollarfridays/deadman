"""Which probes a collector runs, and their arguments: a fact about a file.

**The whole point is that adding a surface on a new machine does not mean
editing the collector.** A new Mac with a different disk history path or a
different brief log location is a new config file, never a new deploy of
this package. What *does* still live in code is :data:`PROBE_TYPES` — the
one place a new *kind* of probe is registered once, by name, before any
config file can name it. That is a narrower seam than "every machine's
argument list is code", and it is the one this module draws the line at.

**A malformed config fails loudly, naming the offending key.** The failure
mode being designed against is silent: a typo in a config file that a
laxer parser shrugs off leaves the collector running with an empty probe
list, sweeping nothing, forever, with no error anywhere. Every refusal below
names the specific key or index that is wrong, so the fix is one line away
from the exception message.

**Argument coercion is generic, not per-probe.** A JSON config can only carry
strings, numbers, booleans, objects and arrays — it has no ``Path`` type. Both
:class:`~deadman.probes.disk.DiskProbe` and
:class:`~deadman.probes.morning_brief.MorningBriefProbe` take ``Path``
fields, and a future probe registered here will too. Rather than hand-coding
which argument name means "this is a path" for every probe type,
:func:`build_probes` reads the target dataclass's own field annotations and
converts a string into a ``Path`` wherever the field says ``Path`` — one
mechanism, good for every probe this module will ever register.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from deadman.probes.base import Probe
from deadman.probes.disk import DiskProbe
from deadman.probes.morning_brief import MorningBriefProbe

#: Where a collector spools evidence it could not deliver, absent an
#: explicit ``spool_dir`` in the config file.
DEFAULT_SPOOL_DIR = Path("/var/lib/deadman/collector/spool")

#: Probe types a config file may name, mapped to the constructor a
#: :class:`ProbeSpec` builds. Registering a *kind* of probe is code; naming
#: which of these to run, and with what arguments, on a given machine is the
#: config file's job.
PROBE_TYPES: dict[str, Callable[..., Probe]] = {
    "disk": DiskProbe,
    "morning_brief": MorningBriefProbe,
}

_REQUIRED_TOP_KEYS = ("collector_id", "ingest_url", "probes")


class ConfigError(ValueError):
    """The config file is not one this collector can run.

    Always names the specific key or probe index that is wrong, so a
    misconfigured collector fails at startup with a fixable message rather
    than starting up and silently sweeping nothing.
    """


@dataclass(frozen=True)
class ProbeSpec:
    """One entry from the config file's ``probes`` array, not yet built."""

    type: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CollectorConfig:
    """A parsed, validated config file."""

    collector_id: str
    ingest_url: str
    probes: tuple[ProbeSpec, ...]
    spool_dir: Path


def load_config(path: Path) -> CollectorConfig:
    """Read and parse a config file, or raise :class:`ConfigError`."""
    try:
        raw = path.read_text()
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    return parse_config(payload)


def parse_config(payload: Any) -> CollectorConfig:
    """Validate an already-parsed payload into a :class:`CollectorConfig`."""
    if not isinstance(payload, Mapping):
        raise ConfigError("config must be a JSON object")

    for key in _REQUIRED_TOP_KEYS:
        if key not in payload:
            raise ConfigError(f"config is missing required key {key!r}")

    collector_id = _require_str(payload, "collector_id")
    ingest_url = _require_str(payload, "ingest_url")

    raw_probes = payload["probes"]
    if not isinstance(raw_probes, list) or not raw_probes:
        raise ConfigError("config key 'probes' must be a non-empty array")

    spool_dir = payload.get("spool_dir", str(DEFAULT_SPOOL_DIR))
    if not isinstance(spool_dir, str) or not spool_dir.strip():
        raise ConfigError("config key 'spool_dir' must be a non-empty string")

    return CollectorConfig(
        collector_id=collector_id,
        ingest_url=ingest_url.rstrip("/"),
        probes=tuple(_parse_probe_spec(i, entry) for i, entry in enumerate(raw_probes)),
        spool_dir=Path(spool_dir),
    )


def _require_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"config key {key!r} must be a non-empty string")
    return value


def _parse_probe_spec(index: int, entry: Any) -> ProbeSpec:
    if not isinstance(entry, Mapping):
        raise ConfigError(f"config key 'probes[{index}]' must be a JSON object")
    probe_type = entry.get("type")
    if not isinstance(probe_type, str) or not probe_type.strip():
        raise ConfigError(f"config key 'probes[{index}].type' must be a non-empty string")
    args = entry.get("args", {})
    if not isinstance(args, Mapping):
        raise ConfigError(f"config key 'probes[{index}].args' must be a JSON object")
    return ProbeSpec(type=probe_type, args=dict(args))


def build_probes(specs: tuple[ProbeSpec, ...]) -> list[Probe]:
    """The real probe instances a config file's ``probes`` array names."""
    return [_build_probe(spec) for spec in specs]


def _build_probe(spec: ProbeSpec) -> Probe:
    ctor = PROBE_TYPES.get(spec.type)
    if ctor is None:
        raise ConfigError(
            f"config key 'probes[].type' names {spec.type!r}, which is not a known probe "
            f"type (known: {sorted(PROBE_TYPES)})"
        )
    try:
        return ctor(**_coerce_args(ctor, spec.args))
    except TypeError as exc:
        raise ConfigError(
            f"config key 'probes[].args' for type {spec.type!r} does not match its "
            f"constructor: {exc}"
        ) from exc


def _coerce_args(ctor: Callable[..., Probe], args: Mapping[str, Any]) -> dict[str, Any]:
    """String arguments become ``Path`` wherever the target field says so.

    JSON has no path type; every probe registered in :data:`PROBE_TYPES` does.
    Reading the field annotations off the dataclass itself means a probe
    added later needs no matching change here — see the module docstring.
    """
    field_types = (
        {f.name: f.type for f in dataclasses.fields(ctor)} if dataclasses.is_dataclass(ctor) else {}
    )
    coerced: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str) and "Path" in str(field_types.get(key, "")):
            coerced[key] = Path(value)
        else:
            coerced[key] = value
    return coerced
