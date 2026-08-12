"""The diagram shows the topology that exists, not the one DM1 had.

`docs/architecture.png` is the first thing a judge sees, on the README and in
the submission, and until DM2 it showed a single process reading four surfaces.
The system stopped working that way the moment the collector shipped: Cloud Run
cannot read a log on a Mac, so every surface is read on one side of a wire and
served on the other, and a relayed claim is weaker than a local one.

A picture that hides that is the most expensive kind of stale documentation,
so the split is asserted rather than eyeballed. The test reads the committed
SVG — the PNG is a build product of it (`scripts/render_diagram.sh`).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
SVG = DOCS / "architecture.svg"
PNG = DOCS / "architecture.png"


def _panel(name: str) -> str:
    """All the text inside the group with this id, as one string."""
    root = ET.parse(SVG).getroot()
    for group in root.iter("{http://www.w3.org/2000/svg}g"):
        if group.get("id") == name:
            return " ".join(t.strip() for t in group.itertext() if t.strip())
    raise AssertionError(
        f"the diagram has no group id={name!r}; the panels are what carry the split"
    )


def test_the_diagram_has_a_collector_side_and_a_service_side():
    collector, service = _panel("collector"), _panel("service")

    assert "kevin-mac" in collector
    assert "900s" in collector, "the sweep cadence is the detection latency; it belongs on the page"
    assert "Cloud Run" in service


def test_each_surface_is_shown_on_the_side_of_the_wire_it_is_read_on():
    """The load-bearing claim. `cron:morning-brief` is read on the Mac and is
    *unobservable* from Cloud Run, and a diagram that draws it once, in the
    middle, is the one that makes a reader think the service reads the log."""
    collector, service = _panel("collector"), _panel("service")

    assert "cron:morning-brief" in collector
    assert "host:mac/disk" in collector
    assert "local_artifact" in collector

    assert "host:disk/" in service
    assert "unobservable" in service.lower(), (
        "the service's own copy of cron:morning-brief reads UNOBSERVABLE, and "
        "showing that is how the picture proves absence is a state"
    )


def test_the_wire_says_what_crossing_it_costs_a_claim():
    wire = _panel("wire")

    assert "/evidence" in wire
    assert "reported" in wire, "arrival caps every relayed row at the weakest method"


def test_the_png_is_a_build_product_of_the_committed_svg():
    render = (DOCS.parent / "scripts" / "render_diagram.sh").read_text()

    assert PNG.exists() and PNG.stat().st_size > 10_000
    assert "architecture.svg" in render and "architecture.png" in render

    height = ET.parse(SVG).getroot().get("height")
    assert height is not None and f"1280,{height}" in render, (
        "the screenshot window must match the SVG canvas, or the render crops it"
    )
