"""Where the Firestore backend keeps the alert send record, exactly.

The contract suite proves the behaviour on both backends. This pins the one
thing only Firestore has, a document path, because the two ways to get it
wrong are both silent: an id encoded twice addresses a different document
(so every instance reads "never sent" and pages on every sweep), and a record
written into the ``evidence`` collection is published on the board.
"""

from __future__ import annotations

from firestore_double import FakeFirestoreClient

from deadman.store.firestore import (
    ALERT_STATE_COLLECTION,
    COLLECTION,
    FirestoreEvidenceStore,
    surface_key,
)


def test_the_send_record_is_one_document_in_its_own_collection_encoded_once():
    client = FakeFirestoreClient()
    store = FirestoreEvidenceStore(client=client)

    store.save_alert_state("host:mac/disk", {"state": "fault", "sends": 1})

    assert ALERT_STATE_COLLECTION == "alert_state"
    assert surface_key("host:mac/disk") == "host%3Amac%2Fdisk"
    written = {
        snapshot.id: snapshot.to_dict() for snapshot in client.collection("alert_state").stream()
    }
    assert written == {"host%3Amac%2Fdisk": {"state": "fault", "sends": 1}}
    assert list(client.collection(COLLECTION).stream()) == []


def test_a_second_instance_reads_what_the_first_wrote():
    """Two store objects over one client share nothing but the database."""
    client = FakeFirestoreClient()
    FirestoreEvidenceStore(client=client).save_alert_state("a:one", {"sends": 3})

    assert FirestoreEvidenceStore(client=client).load_alert_state("a:one") == {"sends": 3}
