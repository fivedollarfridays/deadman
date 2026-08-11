"""The security audit's findings, as tests.

Each class here is one finding from the audit that blocked the DM2 PR, written
as the behaviour that was missing rather than as a patch description. They are
grouped so a future reader can tell *which* argument each guard is defending,
because several of these look like ordinary input validation and are not: a
future-dated ``read_at`` and an unbounded ``detail`` on the public board are
both ways for this project to produce exactly the false green it exists to
argue against.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from deadman.evidence.model import Evidence, Method, Observation
from deadman.ingest import auth as ingest_auth
from deadman.ingest.arrival import REPORTED_METHOD, WIRE_ROW_ID, on_arrival
from deadman.ingest.wire import MAX_SURFACES, WireError, decode_batch, decode_row
from deadman.scheduled import auth as scheduled_auth
from deadman.store.base import encode, row_id

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _row(**over) -> dict:
    base = {
        "surface": "host:mac/disk",
        "observation": "healthy",
        "method": "local_artifact",
        "summary": "80GB free",
        "source": "shutil.disk_usage('/')",
        "read_at": (NOW - timedelta(minutes=1)).isoformat(),
        "detail": {"free_gb": 80.0},
    }
    base.update(over)
    return base


def _batch(rows: list[dict], **over) -> dict:
    base = {
        "version": 1,
        "collector_id": "mac-mini",
        "signed_at": NOW.isoformat(),
        "rows": rows,
    }
    base.update(over)
    return base


class TestFutureReadAtCannotPinASurfaceFresh:
    """Audit finding #2, and the most serious of the set.

    ``_judge_surface`` computes ``age = moment - read_at`` and asks only
    whether it *exceeds* the silence window. A future-dated ``read_at`` makes
    the age negative, which is never greater than the window, so the row is
    returned as current forever — and because the store orders by ``read_at``,
    it also stays newest forever. No attacker is required; a collector with a
    forward-skewed clock does it by accident.
    """

    def test_a_far_future_read_at_is_refused_at_the_wire(self):
        with pytest.raises(WireError, match="ahead|future|skew"):
            decode_row(_row(read_at=datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat()), now=NOW)

    def test_a_small_forward_skew_is_still_accepted(self):
        """Real clocks disagree slightly; only implausible futures are refused."""
        nudged = (NOW + timedelta(seconds=5)).isoformat()
        assert decode_row(_row(read_at=nudged), now=NOW).surface == "host:mac/disk"

    def test_a_stored_future_row_reads_unobservable_not_fresh(self):
        """Defence in depth: rows predating this guard are already stored."""
        from deadman.verify.collector_liveness import _judge_surface
        from deadman.verify.expectations import CollectorExpectation

        future = Evidence(
            surface="host:mac/disk",
            observation=Observation.HEALTHY,
            method=Method.REPORTED,
            summary="all good",
            source="collector",
            read_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
            detail={},
        )
        expectation = CollectorExpectation(
            collector_id="mac-mini", interval_seconds=300.0, surfaces=("host:mac/disk",)
        )

        kind, row = _judge_surface("host:mac/disk", future, expectation, NOW)

        assert kind != "fresh"
        assert row.observation is Observation.UNOBSERVABLE


class TestTheBoardDoesNotRepublishTheEstate:
    """Audit finding #1. ``GET /`` is unauthenticated and already published."""

    def test_absolute_paths_in_detail_are_withheld(self):
        from deadman.service import _evidence_row

        evidence = Evidence(
            surface="brief:morning",
            observation=Observation.FAULT,
            method=Method.REPORTED,
            summary="no brief in 162h",
            source="probe:MorningBriefProbe",
            read_at=NOW,
            detail={"path": "/Users/kevinmasterson/ops/data/brief-send-log.jsonl"},
        )

        published = _evidence_row(evidence)

        assert "kevinmasterson" not in str(published)
        assert "path" in published["detail"].get("withheld", [])

    def test_collector_identity_is_withheld(self):
        from deadman.service import _evidence_row

        arrived = on_arrival(
            Evidence(
                surface="host:mac/disk",
                observation=Observation.HEALTHY,
                method=Method.LOCAL_ARTIFACT,
                summary="80GB free",
                source="shutil.disk_usage('/')",
                read_at=NOW,
                detail={"free_gb": 80.0},
            ),
            "mac-mini",
            NOW,
        )

        published = _evidence_row(arrived)

        assert "mac-mini" not in str(published)
        assert published["detail"]["free_gb"] == 80.0, "operational numbers still publish"

    def test_a_path_shaped_source_is_reduced(self):
        from deadman.service import _evidence_row

        evidence = Evidence(
            surface="brief:morning",
            observation=Observation.FAULT,
            method=Method.LOCAL_ARTIFACT,
            summary="stale",
            source="/Users/kevinmasterson/ops/data/brief-send-log.jsonl",
            read_at=NOW,
            detail={},
        )

        assert "kevinmasterson" not in str(_evidence_row(evidence))


class TestTheClientCannotChooseARowsIdentity:
    """Audit finding #6.

    Guarded at the wire rather than at annotation, and the distinction matters.
    ``on_arrival`` deliberately *preserves* these keys when it finds them, so
    that re-annotating an already-annotated row keeps the original claim
    instead of laundering it into a fresh one. That preservation is only safe
    if a client cannot put them there in the first place, so the untrusted
    input is stripped at the boundary and the internal invariant is left alone.
    """

    @pytest.mark.parametrize(
        "key,value",
        [
            (WIRE_ROW_ID, "attacker-chosen"),
            (REPORTED_METHOD, "destination_api"),
            ("collector_id", "not-my-name"),
            ("received_at", "2099-01-01T00:00:00+00:00"),
        ],
    )
    def test_service_owned_detail_keys_are_stripped_from_the_wire(self, key, value):
        decoded = decode_row(_row(detail={key: value, "free_gb": 80.0}), now=NOW)

        assert key not in decoded.detail
        assert decoded.detail["free_gb"] == 80.0, "the collector's own detail survives"

    def test_the_identity_the_service_computes_is_the_one_that_is_stored(self):
        decoded = decode_row(_row(detail={WIRE_ROW_ID: "attacker-chosen"}), now=NOW)

        stored = on_arrival(decoded, "mac-mini", NOW)

        assert stored.detail[WIRE_ROW_ID] == row_id(decoded)
        assert stored.detail[WIRE_ROW_ID] != "attacker-chosen"

    def test_a_claimed_method_cannot_be_inflated_through_detail(self):
        decoded = decode_row(
            _row(method="local_artifact", detail={REPORTED_METHOD: "destination_api"}), now=NOW
        )

        assert on_arrival(decoded, "mac-mini", NOW).detail[REPORTED_METHOD] == "local_artifact"


class TestSurfaceIdsAreValidated:
    """Audit finding #7. Firestore rejects these as document ids, so an
    unvalidated surface is a 500 *after* the request already passed auth."""

    @pytest.mark.parametrize(
        "bad", ["", "   ", "..", ".", "__x__", "a b", "a\nb", "-leading", "x" * 300]
    )
    def test_unusable_surface_ids_are_refused(self, bad):
        with pytest.raises(WireError):
            decode_row(_row(surface=bad), now=NOW)

    @pytest.mark.parametrize("good", ["host:mac/disk", "brief:morning", "sms:relay"])
    def test_real_surface_ids_still_pass(self, good):
        """``/`` is legitimate here — ``surface_key`` percent-encodes it before
        Firestore ever sees it, so refusing it would break every real id."""
        assert decode_row(_row(surface=good), now=NOW).surface == good

    @pytest.mark.parametrize("field", ["summary", "source"])
    def test_oversized_text_fields_are_refused(self, field):
        with pytest.raises(WireError):
            decode_row(_row(**{field: "x" * 100_000}), now=NOW)


class TestBatchesCannotAmplifyReads:
    """Audit finding #10. The replay check issues one history query per
    distinct surface, so 500 distinct surfaces is up to 100k billed Firestore
    reads for a single request."""

    def test_too_many_distinct_surfaces_is_refused(self):
        rows = [_row(surface=f"host:mac/s{i}") for i in range(MAX_SURFACES + 1)]
        with pytest.raises(WireError, match="surface"):
            decode_batch(_batch(rows), now=NOW)

    def test_a_realistic_sweep_still_passes(self):
        rows = [_row(surface=f"host:mac/s{i}") for i in range(5)]
        assert len(decode_batch(_batch(rows), now=NOW).rows) == 5


class TestNonAsciiCredentialsAreRejectedNotCrashed:
    """Audit finding #5. WSGI header values are latin-1 ``str``, and
    ``hmac.compare_digest`` raises ``TypeError`` on non-ASCII — an
    unauthenticated stranger's route to an unhandled 500, contradicting both
    docstrings' promise never to raise for bad input."""

    def test_ingest_signature_with_non_ascii_is_an_auth_error(self):
        with pytest.raises(ingest_auth.AuthError):
            ingest_auth.check_signature(b"{}", "ü" * 64, b"secret")

    def test_scheduler_bearer_with_non_ascii_is_an_auth_error(self):
        with pytest.raises(scheduled_auth.SchedulerAuthError):
            scheduled_auth.check_secret("Bearer ü", "expected")


class TestTheCollectorRefusesCleartextIngest:
    """Audit finding #8. An ``http://`` endpoint ships evidence and its MAC in
    the clear, making on-path capture and replay inside the freshness window
    trivial."""

    def test_an_http_ingest_url_is_refused(self):
        from deadman.collector.config import ConfigError, parse_config

        payload = {
            "collector_id": "mac-mini",
            "ingest_url": "http://deadman.example/evidence",
            "probes": [{"type": "disk", "args": {}}],
        }
        with pytest.raises(ConfigError, match="https"):
            parse_config(payload)

    def test_https_is_accepted(self):
        from deadman.collector.config import parse_config

        payload = {
            "collector_id": "mac-mini",
            "ingest_url": "https://deadman.example/evidence",
            "probes": [{"type": "disk", "args": {}}],
        }
        assert parse_config(payload).ingest_url.startswith("https://")

    def test_localhost_over_http_is_allowed_for_development(self):
        from deadman.collector.config import parse_config

        payload = {
            "collector_id": "mac-mini",
            "ingest_url": "http://localhost:8080",
            "probes": [{"type": "disk", "args": {}}],
        }
        assert parse_config(payload).ingest_url == "http://localhost:8080"


class TestACollectorMayOnlyReportItsOwnSurfaces:
    """Audit finding #3, cheap half. Per-collector secrets are DM3, but the
    surface declaration already exists in ``expectations.py``, so binding a
    batch to it costs nothing and turns "compromise one laptop, forge HEALTHY
    for the whole estate" into "forge it for the surfaces that laptop already
    reports"."""

    def _endpoint(self, expectations):
        from deadman.ingest.endpoint import IngestEndpoint
        from deadman.store.memory import InMemoryEvidenceStore

        return IngestEndpoint(
            store=InMemoryEvidenceStore(),
            secret=b"secret",
            expectations=expectations,
        )

    def test_a_row_for_an_undeclared_surface_is_refused(self):
        from deadman.ingest.wire import Batch
        from deadman.verify.expectations import CollectorExpectation

        endpoint = self._endpoint(
            (
                CollectorExpectation(
                    collector_id="mac-mini", interval_seconds=300.0, surfaces=("host:mac/disk",)
                ),
            )
        )
        batch = Batch(
            collector_id="mac-mini",
            signed_at=NOW,
            rows=(decode_row(_row(surface="host:rig/disk"), now=NOW),),
        )

        with pytest.raises(WireError, match="declare"):
            endpoint.check_declared(batch)

    def test_a_declared_surface_passes(self):
        from deadman.ingest.wire import Batch
        from deadman.verify.expectations import CollectorExpectation

        endpoint = self._endpoint(
            (
                CollectorExpectation(
                    collector_id="mac-mini", interval_seconds=300.0, surfaces=("host:mac/disk",)
                ),
            )
        )
        batch = Batch(
            collector_id="mac-mini",
            signed_at=NOW,
            rows=(decode_row(_row(surface="host:mac/disk"), now=NOW),),
        )

        endpoint.check_declared(batch)

    def test_no_expectations_configured_means_no_binding(self):
        """Backward compatible: an estate that has not declared anything yet
        is not locked out of ingesting."""
        from deadman.ingest.wire import Batch

        endpoint = self._endpoint(None)
        batch = Batch(
            collector_id="anyone",
            signed_at=NOW,
            rows=(decode_row(_row(), now=NOW),),
        )

        endpoint.check_declared(batch)


class TestTheWireStillRoundTrips:
    """The guards above must not break the format they protect."""

    def test_an_encoded_evidence_decodes_back(self):
        evidence = Evidence(
            surface="host:mac/disk",
            observation=Observation.HEALTHY,
            method=Method.LOCAL_ARTIFACT,
            summary="80GB free",
            source="shutil.disk_usage('/')",
            read_at=NOW - timedelta(minutes=1),
            detail={"free_gb": 80.0},
        )

        assert decode_row(encode(evidence), now=NOW) == evidence
