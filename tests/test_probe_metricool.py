"""Locks the Metricool probe to the spike's conclusions.

See ``docs/metricool-verification.md``. The findings that drive these tests:
Instagram permalinks return 200 for a real post and 200 for a nonexistent
one, so that destination is unreadable and no amount of scheduler confidence
changes it; X permalinks return 200/404 and are readable.

So the distinctions under test are not the happy path. They are:

* scheduler-reported success, on its own, is never ``HEALTHY``;
* absent-at-destination is ``FAULT`` and names the post;
* cannot-read-the-destination is ``UNOBSERVABLE``, never ``FAULT``;
* an opaque platform is not fetched at all, and cannot yield ``HEALTHY``.

No test touches the network. The scheduler and the destination reader are
both injected, and ``tests/conftest.py`` blocks sockets suite-wide anyway.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from deadman.evidence.model import Method, Observation
from deadman.probes.base import run_probe
from deadman.probes.destinations import DestinationRead, DestinationState, PermalinkReader
from deadman.probes.metricool import MetricoolProbe, ScheduledPost


def _post(
    post_id: str = "post-1",
    platform: str = "x",
    hours_ago: float = 2.0,
    permalink: str | None = None,
) -> ScheduledPost:
    return ScheduledPost(
        post_id=post_id,
        platform=platform,
        permalink=permalink or f"https://x.com/fwtx_dao/status/{post_id}",
        reported_status="published",
        reported_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )


class _Scheduler:
    """Stands in for Metricool. Reports whatever it is told to report."""

    def __init__(self, posts: list[ScheduledPost] | None = None) -> None:
        self._posts = posts if posts is not None else []
        self.calls = 0

    def recently_published(self) -> list[ScheduledPost]:
        self.calls += 1
        return list(self._posts)


def _post_id_of(permalink: str) -> str:
    """The fakes key off the permalink's last segment, since ``_post`` builds
    permalinks as ``.../status/<post_id>``."""
    return permalink.rstrip("/").rsplit("/", 1)[-1]


class _Reader:
    """Stands in for the destination. Records what it was asked to read, so a
    test can assert an opaque platform was never fetched."""

    def __init__(
        self, *, state: DestinationState, method: Method = Method.DESTINATION_PUBLIC
    ) -> None:
        self._state = state
        self._method = method
        self.read_ids: list[str] = []

    def read(self, platform: str, permalink: str | None) -> DestinationRead:
        self.read_ids.append(_post_id_of(permalink or ""))
        return DestinationRead(state=self._state, method=self._method, detail={"http_status": 200})


class _PerPostReader:
    """Different answer per post id, for the mixed-batch precedence tests."""

    def __init__(self, states: dict[str, DestinationState]) -> None:
        self._states = states
        self.read_ids: list[str] = []

    def read(self, platform: str, permalink: str | None) -> DestinationRead:
        post_id = _post_id_of(permalink or "")
        self.read_ids.append(post_id)
        return DestinationRead(
            state=self._states[post_id], method=Method.DESTINATION_PUBLIC, detail={}
        )


class _RaisingReader:
    def read(self, platform: str, permalink: str | None) -> DestinationRead:
        raise ConnectionError("simulated DNS failure")


# --- the three cases the acceptance criteria name -------------------------


def test_post_confirmed_at_destination_is_healthy_on_destination_evidence() -> None:
    reader = _Reader(state=DestinationState.PRESENT)
    probe = MetricoolProbe(brand="fwtx_dao", scheduler=_Scheduler([_post()]), reader=reader)

    evidence = probe.observe()

    assert evidence.observation is Observation.HEALTHY
    # The verdict must rest on destination evidence, not on the report.
    assert evidence.method is Method.DESTINATION_PUBLIC
    assert reader.read_ids == ["post-1"]


def test_post_reported_published_but_absent_is_fault_naming_the_post_id() -> None:
    probe = MetricoolProbe(
        brand="fwtx_dao",
        scheduler=_Scheduler([_post(post_id="roundtable-42")]),
        reader=_Reader(state=DestinationState.ABSENT),
    )

    evidence = probe.observe()

    assert evidence.observation is Observation.FAULT
    # Naming the post is the acceptance criterion: an operator has to be able
    # to go straight to the thing that did not publish.
    assert "roundtable-42" in evidence.summary
    assert evidence.detail["absent_post_ids"] == ["roundtable-42"]
    assert evidence.method is Method.DESTINATION_PUBLIC


def test_unreachable_destination_is_unobservable_never_fault() -> None:
    probe = MetricoolProbe(
        brand="fwtx_dao",
        scheduler=_Scheduler([_post(post_id="post-9")]),
        reader=_Reader(state=DestinationState.UNREADABLE),
    )

    evidence = probe.observe()

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.observation is not Observation.FAULT
    assert "post-9" in evidence.detail["unverified_post_ids"]


# --- scheduler-reported success alone is never HEALTHY --------------------


def test_opaque_platform_is_unobservable_and_the_destination_is_never_fetched() -> None:
    """Instagram is unreadable per the spike, so a reported-published
    Instagram post yields a declared blind spot. Fetching the permalink would
    return 200 for an absent post, so the probe must not fetch it at all."""
    reader = _Reader(state=DestinationState.PRESENT)
    probe = MetricoolProbe(
        brand="fwtx_dao",
        scheduler=_Scheduler([_post(post_id="ig-1", platform="instagram")]),
        reader=reader,
    )

    evidence = probe.observe()

    assert evidence.observation is Observation.UNOBSERVABLE
    assert reader.read_ids == []
    assert evidence.method is Method.REPORTED


def test_present_read_on_a_weak_method_cannot_yield_healthy() -> None:
    """Structural guard on the strongest acceptance criterion. A reader that
    says "present" but admits it learned that from a report is a heartbeat,
    and no arrangement of it may produce HEALTHY."""
    reader = _Reader(state=DestinationState.PRESENT, method=Method.REPORTED)
    probe = MetricoolProbe(brand="fwtx_dao", scheduler=_Scheduler([_post()]), reader=reader)

    evidence = probe.observe()

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.observation is not Observation.HEALTHY
    # The report has to say why, or the blind spot looks like a glitch.
    assert "reported" in evidence.detail["unverified_reasons"]["post-1"]


def test_unknown_platform_fails_closed_to_unobservable() -> None:
    probe = MetricoolProbe(
        brand="fwtx_dao",
        scheduler=_Scheduler([_post(post_id="tt-1", platform="some-new-network")]),
        reader=_Reader(state=DestinationState.PRESENT),
    )

    assert probe.observe().observation is Observation.UNOBSERVABLE


def test_an_empty_schedule_is_unobservable_not_healthy() -> None:
    """Nothing reported means nothing verified. Silence is not health -- the
    same trap the morning brief probe is built around."""
    probe = MetricoolProbe(
        brand="fwtx_dao",
        scheduler=_Scheduler([]),
        reader=_Reader(state=DestinationState.PRESENT),
    )

    evidence = probe.observe()

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.observation is not Observation.HEALTHY


# --- precedence and windowing --------------------------------------------


def test_one_absent_post_among_confirmed_ones_still_yields_fault() -> None:
    posts = [_post(post_id="a"), _post(post_id="b"), _post(post_id="c")]
    reader = _PerPostReader(
        {
            "a": DestinationState.PRESENT,
            "b": DestinationState.ABSENT,
            "c": DestinationState.PRESENT,
        }
    )
    probe = MetricoolProbe(brand="fwtx_dao", scheduler=_Scheduler(posts), reader=reader)

    evidence = probe.observe()

    assert evidence.observation is Observation.FAULT
    assert evidence.detail["absent_post_ids"] == ["b"]
    assert "b" in evidence.summary


def test_a_confirmed_absence_outranks_an_unreadable_sibling() -> None:
    """We did learn this surface is broken. The blindness on the sibling is
    recorded in the detail rather than downgrading a known fault."""
    posts = [_post(post_id="gone"), _post(post_id="murky")]
    reader = _PerPostReader(
        {"gone": DestinationState.ABSENT, "murky": DestinationState.UNREADABLE}
    )
    probe = MetricoolProbe(brand="fwtx_dao", scheduler=_Scheduler(posts), reader=reader)

    evidence = probe.observe()

    assert evidence.observation is Observation.FAULT
    assert evidence.detail["absent_post_ids"] == ["gone"]
    assert evidence.detail["unverified_post_ids"] == ["murky"]


def test_one_unverified_post_prevents_a_healthy_verdict_for_the_batch() -> None:
    posts = [_post(post_id="ok"), _post(post_id="blind")]
    reader = _PerPostReader(
        {"ok": DestinationState.PRESENT, "blind": DestinationState.UNREADABLE}
    )
    probe = MetricoolProbe(brand="fwtx_dao", scheduler=_Scheduler(posts), reader=reader)

    evidence = probe.observe()

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.detail["confirmed_post_ids"] == ["ok"]


def test_a_post_inside_the_grace_period_is_not_yet_called_absent() -> None:
    """Propagation delay is not a fault. Verifying a post published seconds
    ago manufactures a false FAULT, so recent posts are not yet due."""
    reader = _Reader(state=DestinationState.ABSENT)
    probe = MetricoolProbe(
        brand="fwtx_dao",
        scheduler=_Scheduler([_post(post_id="fresh", hours_ago=0.01)]),
        reader=reader,
        grace_minutes=10.0,
    )

    evidence = probe.observe()

    assert evidence.observation is not Observation.FAULT
    assert evidence.detail["pending_grace_post_ids"] == ["fresh"]
    assert reader.read_ids == []


def test_a_post_older_than_the_window_is_not_re_verified() -> None:
    reader = _Reader(state=DestinationState.ABSENT)
    probe = MetricoolProbe(
        brand="fwtx_dao",
        scheduler=_Scheduler([_post(post_id="ancient", hours_ago=200.0)]),
        reader=reader,
        window_hours=48.0,
    )

    evidence = probe.observe()

    assert evidence.observation is not Observation.FAULT
    assert reader.read_ids == []


# --- never-raise contract -------------------------------------------------


def test_a_raising_reader_is_unobservable_not_fault() -> None:
    probe = MetricoolProbe(
        brand="fwtx_dao", scheduler=_Scheduler([_post(post_id="boom")]), reader=_RaisingReader()
    )

    evidence = probe.observe()

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.observation is not Observation.FAULT


def test_a_raising_scheduler_is_contained_by_the_probe_contract() -> None:
    class _RaisingScheduler:
        def recently_published(self) -> list[ScheduledPost]:
            raise TimeoutError("metricool api timed out")

    probe = MetricoolProbe(
        brand="fwtx_dao",
        scheduler=_RaisingScheduler(),
        reader=_Reader(state=DestinationState.PRESENT),
    )

    evidence = run_probe(probe)

    assert evidence.observation is Observation.UNOBSERVABLE
    assert evidence.surface == "metricool:fwtx_dao"


def test_the_surface_id_is_brand_keyed_and_stable() -> None:
    probe = MetricoolProbe(
        brand="fwtx_dao", scheduler=_Scheduler([]), reader=_Reader(state=DestinationState.PRESENT)
    )

    assert probe.surface == "metricool:fwtx_dao"
    assert probe.observe().surface == "metricool:fwtx_dao"


# --- the permalink reader's status mapping (no network) -------------------


def test_permalink_reader_maps_200_to_present_and_404_to_absent() -> None:
    responses = {"https://x.com/fwtx_dao/status/1": (200, "ok"), "gone": (404, "not found")}
    reader = PermalinkReader(fetch=lambda url: responses[url])

    present = reader.read("x", "https://x.com/fwtx_dao/status/1")
    absent = reader.read("x", "gone")

    assert present.state is DestinationState.PRESENT
    assert present.method is Method.DESTINATION_PUBLIC
    assert absent.state is DestinationState.ABSENT


def test_permalink_reader_maps_rate_limits_and_server_errors_to_unreadable() -> None:
    for status in (429, 500, 503, 403, 0):
        reader = PermalinkReader(fetch=lambda url, s=status: (s, ""))

        read = reader.read("x", "https://x.com/fwtx_dao/status/1")

        assert read.state is DestinationState.UNREADABLE, f"status {status}"


def test_permalink_reader_refuses_to_fetch_an_opaque_platform() -> None:
    """The last line of defense. On Instagram a 200 means nothing, so mapping
    it to PRESENT would manufacture the exact false HEALTHY this project
    exists to catch -- even if a future caller wires the reader up directly."""
    fetched: list[str] = []

    def _fetch(url: str) -> tuple[int, str]:
        fetched.append(url)
        return (200, "instagram login wall")

    reader = PermalinkReader(fetch=_fetch)

    read = reader.read("instagram", "https://www.instagram.com/p/BwrHPjxlseb/")

    assert read.state is DestinationState.UNREADABLE
    assert fetched == []


def test_permalink_reader_maps_a_raising_fetch_to_unreadable() -> None:
    def _fetch(url: str) -> tuple[int, str]:
        raise OSError("connection reset")

    reader = PermalinkReader(fetch=_fetch)

    assert reader.read("x", "https://x.com/fwtx_dao/status/1").state is DestinationState.UNREADABLE


def test_permalink_reader_treats_a_missing_permalink_as_unreadable() -> None:
    reader = PermalinkReader(fetch=lambda url: (200, "ok"))

    assert reader.read("x", None).state is DestinationState.UNREADABLE
