"""Authenticated ingest: evidence that crossed a wire, and what it now means.

The surfaces are not where the service is. A collector runs on the machine
whose disk and logs it can actually read (see DM2.3) and ships what it saw to
Cloud Run, which means every real observation this system holds arrives as a
**report of** an observation rather than the observation itself.

That distinction is the whole point of this package, and it is enforced in
:mod:`deadman.ingest.arrival`: the method is never upgraded on arrival. A
service that recorded a collector's local file read as its own local file read
would be asserting it looked at a disk it cannot see — a heartbeat wearing a
hat, which is precisely the failure class deadman exists to catch.

Around that sit three supporting pieces: :mod:`deadman.ingest.wire` (the
format, strictly parsed because the input is remote), :mod:`deadman.ingest.auth`
(HMAC over the raw bytes, a freshness window, and a secret that must exist
before the service will start), and :mod:`deadman.ingest.endpoint` (the WSGI
handler behind ``POST /evidence``).
"""

from __future__ import annotations

from deadman.ingest.arrival import (
    COLLECTOR_ID,
    ON_ARRIVAL,
    RECEIVED_AT,
    REPORTED_METHOD,
    WIRE_ROW_ID,
    arrival_method,
    on_arrival,
)
from deadman.ingest.auth import (
    FRESHNESS_SECONDS,
    SECRET_ENV,
    SIGNATURE_ENVIRON_KEY,
    SIGNATURE_HEADER,
    AuthError,
    IngestNotConfigured,
    secret_from_env,
    sign,
    verify,
)
from deadman.ingest.endpoint import EVIDENCE_PATH, MAX_BODY_BYTES, IngestEndpoint
from deadman.ingest.wire import MAX_ROWS, WIRE_VERSION, Batch, WireError, dumps, loads

__all__ = [
    "COLLECTOR_ID",
    "EVIDENCE_PATH",
    "FRESHNESS_SECONDS",
    "MAX_BODY_BYTES",
    "MAX_ROWS",
    "ON_ARRIVAL",
    "RECEIVED_AT",
    "REPORTED_METHOD",
    "SECRET_ENV",
    "SIGNATURE_ENVIRON_KEY",
    "SIGNATURE_HEADER",
    "WIRE_ROW_ID",
    "WIRE_VERSION",
    "AuthError",
    "Batch",
    "IngestEndpoint",
    "IngestNotConfigured",
    "WireError",
    "arrival_method",
    "dumps",
    "loads",
    "on_arrival",
    "secret_from_env",
    "sign",
    "verify",
]
