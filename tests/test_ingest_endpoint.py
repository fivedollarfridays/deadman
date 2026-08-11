"""``POST /evidence`` end to end, against a real store.

No sockets: the endpoint is exercised through a WSGI ``environ`` exactly as a
server would call it. The store is the in-memory backend, which is a real
:class:`~deadman.store.base.EvidenceStore` and contract-tested as one, so
"stores every row" here means what it means in production.

Two rejection properties get equal weight with the happy path, because a
monitor that accepts bad batches is worse than one that accepts none: every
refusal below is also asserted to have stored *nothing*, and every failure
mode is asserted to be a 4xx rather than a traceback.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from deadman.evidence.model import Evidence, Method, Observation
from deadman.ingest.arrival import COLLECTOR_ID, RECEIVED_AT, REPORTED_METHOD
from deadman.ingest.auth import FRESHNESS_SECONDS, SIGNATURE_ENVIRON_KEY, sign
from deadman.ingest.endpoint import EVIDENCE_PATH, MAX_BODY_BYTES, IngestEndpoint
from deadman.ingest.wire import Batch, dumps
from deadman.store.memory import InMemoryEvidenceStore

SECRET = b"a-shared-secret-for-tests"
NOW = datetime(2026, 8, 11, 7, 0, tzinfo=timezone.utc)
READ_AT = datetime(2026, 8, 11, 6, 56, tzinfo=timezone.utc)


def _evidence(surface: str = "host:mac/disk", **overrides: object) -> Evidence:
    fields: dict[str, object] = {
        "surface": surface,
        "observation": Observation.FAULT,
        "method": Method.LOCAL_ARTIFACT,
        "summary": f"{surface} is unhappy",
        "source": "collector",
        "read_at": READ_AT,
        "detail": {"free_gb": 50.0},
    }
    fields.update(overrides)
    return Evidence(**fields)  # type: ignore[arg-type]


def _batch(*rows: Evidence, signed_at: datetime = NOW) -> Batch:
    return Batch(
        collector_id="mac-studio",
        signed_at=signed_at,
        rows=tuple(rows or (_evidence(),)),
    )


def _endpoint(store: InMemoryEvidenceStore, now: datetime = NOW) -> IngestEndpoint:
    return IngestEndpoint(store=store, secret=SECRET, clock=lambda: now)


def _environ(body: bytes, signature: str | None = None, content_length: int | None = None):
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": EVIDENCE_PATH,
        "CONTENT_LENGTH": str(len(body) if content_length is None else content_length),
        "wsgi.input": io.BytesIO(body),
    }
    if signature is not None:
        environ[SIGNATURE_ENVIRON_KEY] = signature
    return environ


def _post(endpoint: IngestEndpoint, batch: Batch | None = None, **overrides: object):
    body = dumps(batch if batch is not None else _batch())
    signature = overrides.pop("signature", sign(body, SECRET))
    return endpoint.handle(_environ(body, signature, **overrides))  # type: ignore[arg-type]


class TestAcceptedBatch:
    def test_a_correctly_signed_batch_stores_every_row(self):
        store = InMemoryEvidenceStore()
        batch = _batch(_evidence("host:mac/disk"), _evidence("brief:morning"))

        status, payload = _post(_endpoint(store), batch)

        assert status.startswith("200")
        assert payload["stored"] == 2
        assert sorted(store.latest_per_surface()) == ["brief:morning", "host:mac/disk"]

    def test_stored_rows_carry_the_collector_and_an_arrival_time(self):
        store = InMemoryEvidenceStore()

        _post(_endpoint(store))

        stored = store.latest("host:mac/disk")
        assert stored.detail[COLLECTOR_ID] == "mac-studio"
        assert stored.detail[RECEIVED_AT] == NOW.isoformat()
        assert stored.read_at == READ_AT

    def test_the_method_is_downgraded_on_the_row_that_is_actually_stored(self):
        """The rule is enforced at the boundary, not merely available near it.

        Dropping the :func:`~deadman.ingest.arrival.on_arrival` call from the
        endpoint would leave every unit test in
        ``tests/test_ingest_arrival.py`` green and store an upgraded claim.
        """
        store = InMemoryEvidenceStore()

        _post(_endpoint(store), _batch(_evidence(method=Method.DESTINATION_API)))

        stored = store.latest("host:mac/disk")
        assert stored.method is Method.REPORTED
        assert stored.detail[REPORTED_METHOD] == Method.DESTINATION_API.value

    def test_the_collectors_reading_time_is_never_replaced_by_arrival_time(self):
        store = InMemoryEvidenceStore()
        delivered_late = _endpoint(store, now=NOW + timedelta(seconds=FRESHNESS_SECONDS - 1))

        _post(delivered_late)

        assert store.latest("host:mac/disk").read_at == READ_AT


class TestRejection:
    def test_an_unsigned_batch_is_refused_and_stores_nothing(self):
        store = InMemoryEvidenceStore()

        status, payload = _post(_endpoint(store), signature=None)

        assert status.startswith("401")
        assert store.latest_per_surface() == {}
        assert "error" in payload

    def test_a_wrongly_signed_batch_is_refused_and_stores_nothing(self):
        store = InMemoryEvidenceStore()
        body = dumps(_batch())

        status, _payload = _endpoint(store).handle(_environ(body, sign(body, b"wrong")))

        assert status.startswith("401")
        assert store.latest_per_surface() == {}

    def test_a_tampered_row_invalidates_the_signature(self):
        """The MAC covers the bytes, so editing a row after signing is caught."""
        store = InMemoryEvidenceStore()
        body = dumps(_batch())
        signature = sign(body, SECRET)
        tampered = body.replace(b"fault", b"healthy")

        status, _payload = _endpoint(store).handle(_environ(tampered, signature))

        assert status.startswith("401")
        assert store.latest_per_surface() == {}

    def test_a_batch_signed_outside_the_freshness_window_is_stale(self):
        store = InMemoryEvidenceStore()
        old = NOW - timedelta(seconds=FRESHNESS_SECONDS + 60)

        status, payload = _post(_endpoint(store), _batch(signed_at=old))

        assert status.startswith("401")
        assert "stale" in payload["error"]
        assert store.latest_per_surface() == {}

    def test_a_stale_batch_is_refused_even_though_its_signature_is_valid(self):
        """Freshness is a second gate, not an alternative to the MAC."""
        store = InMemoryEvidenceStore()
        ahead = NOW + timedelta(seconds=FRESHNESS_SECONDS + 60)

        status, _payload = _post(_endpoint(store), _batch(signed_at=ahead))

        assert status.startswith("401")
        assert store.latest_per_surface() == {}


class TestMalformedAndOversized:
    def test_a_body_that_is_not_json_is_a_400_not_a_500(self):
        store = InMemoryEvidenceStore()
        body = b"{not json at all"

        status, payload = _endpoint(store).handle(_environ(body, sign(body, SECRET)))

        assert status.startswith("400")
        assert "error" in payload
        assert store.latest_per_surface() == {}

    def test_a_batch_missing_required_fields_is_a_400(self):
        store = InMemoryEvidenceStore()
        payload_dict = json.loads(dumps(_batch()))
        del payload_dict["rows"][0]["method"]
        body = json.dumps(payload_dict).encode()

        status, _payload = _endpoint(store).handle(_environ(body, sign(body, SECRET)))

        assert status.startswith("400")
        assert store.latest_per_surface() == {}

    def test_an_oversized_body_is_refused_before_it_is_read(self):
        store = InMemoryEvidenceStore()
        body = b"x" * 32

        status, payload = _endpoint(store).handle(
            _environ(body, sign(body, SECRET), content_length=MAX_BODY_BYTES + 1)
        )

        assert status.startswith("413")
        assert "error" in payload
        assert store.latest_per_surface() == {}

    def test_a_body_longer_than_its_declared_length_is_still_capped(self):
        """A lying Content-Length must not become an unbounded read."""
        store = InMemoryEvidenceStore()
        body = b"x" * (MAX_BODY_BYTES + 100)

        status, _payload = _endpoint(store).handle(_environ(body, "00", content_length=8))

        assert status.startswith("413")
        assert store.latest_per_surface() == {}

    def test_a_non_integer_content_length_is_a_400(self):
        store = InMemoryEvidenceStore()
        environ = _environ(b"{}", "00")
        environ["CONTENT_LENGTH"] = "banana"

        status, _payload = _endpoint(store).handle(environ)

        assert status.startswith("400")

    def test_an_empty_body_is_a_4xx(self):
        store = InMemoryEvidenceStore()

        status, _payload = _endpoint(store).handle(_environ(b"", sign(b"", SECRET)))

        assert status.startswith("4")
        assert store.latest_per_surface() == {}

    @pytest.mark.parametrize("missing", ["wsgi.input", "CONTENT_LENGTH"])
    def test_a_request_without_a_body_does_not_raise(self, missing: str):
        store = InMemoryEvidenceStore()
        environ = _environ(b"", "00")
        del environ[missing]

        status, _payload = _endpoint(store).handle(environ)

        assert status.startswith("4")


class TestReplay:
    def test_a_replayed_identical_batch_does_not_grow_the_history(self):
        """The collector's retry after a failed delivery must not manufacture
        a second observation, and so must not manufacture a trend."""
        store = InMemoryEvidenceStore()
        endpoint = _endpoint(store)
        batch = _batch(_evidence("host:mac/disk"), _evidence("brief:morning"))

        _post(endpoint, batch)
        before = len(store.history("host:mac/disk"))
        status, payload = _post(endpoint, batch)

        assert status.startswith("200")
        assert len(store.history("host:mac/disk")) == before == 1
        assert payload["stored"] == 0
        assert payload["duplicates"] == 2

    def test_replay_is_idempotent_even_when_arrival_time_has_moved_on(self):
        """The dedupe key is the observation, not our bookkeeping about it.

        Keying on the stored row would fail here, because the stored row
        carries ``received_at`` and that differs on the second delivery.
        """
        store = InMemoryEvidenceStore()
        batch = _batch()

        _post(_endpoint(store, now=NOW), batch)
        _post(_endpoint(store, now=NOW + timedelta(seconds=90)), batch)

        assert len(store.history("host:mac/disk")) == 1

    def test_a_batch_repeating_one_row_twice_stores_it_once(self):
        store = InMemoryEvidenceStore()
        row = _evidence()

        _post(_endpoint(store), _batch(row, row))

        assert len(store.history("host:mac/disk")) == 1

    def test_a_genuinely_new_reading_of_the_same_surface_is_still_recorded(self):
        """Idempotency must not become deafness.

        A dedupe that keyed on surface alone would pass every test above and
        silently discard every subsequent sweep.
        """
        store = InMemoryEvidenceStore()
        endpoint = _endpoint(store)

        _post(endpoint, _batch(_evidence()))
        _post(endpoint, _batch(_evidence(read_at=READ_AT + timedelta(minutes=5))))

        assert len(store.history("host:mac/disk")) == 2
