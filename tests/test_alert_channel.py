"""The alarm must not travel over anything deadman watches.

This is the whole lesson of the nine-day outage stated as a constraint. The
morning brief was both the failing surface and the channel that would have
reported the failure, so its death was self-concealing. Any monitor that
routes its alarms through a monitored surface has the same hole, and the only
reliable moment to catch it is configuration time, because the moment you need
the alert is exactly the moment the channel is down.
"""

from __future__ import annotations

import pytest

from deadman.remediate.alert import AlertChannel, AlertChannelInvalid

MONITORED = ("cron:morning-brief", "sms:relay", "metricool:fwtx_dao", "host:disk/")


def _sink():
    sent: list[str] = []
    return sent, sent.append


def test_an_unmonitored_transport_configures_and_sends():
    sent, send = _sink()
    channel = AlertChannel(transport="email:ops@example.com", send=send, monitored=MONITORED)

    channel.alert("disk runway 3 days")

    assert sent == ["disk runway 3 days"]


def test_configuring_a_monitored_surface_as_the_transport_raises_at_startup():
    _, send = _sink()

    with pytest.raises(AlertChannelInvalid) as exc:
        AlertChannel(transport="cron:morning-brief", send=send, monitored=MONITORED)

    assert "cron:morning-brief" in str(exc.value)


def test_a_different_id_on_a_monitored_rail_still_raises():
    # "sms:relay" is watched, so "sms:backup" is not out of band: it is the
    # same rail wearing a different name. If the phone relay is dead, an alert
    # over SMS does not arrive, whatever the destination is called.
    _, send = _sink()

    with pytest.raises(AlertChannelInvalid) as exc:
        AlertChannel(transport="sms:backup-number", send=send, monitored=MONITORED)

    assert "sms" in str(exc.value)


def test_the_error_says_what_to_do_about_it():
    _, send = _sink()

    with pytest.raises(AlertChannelInvalid) as exc:
        AlertChannel(transport="sms:relay", send=send, monitored=MONITORED)

    message = str(exc.value)
    assert "sms:relay" in message
    assert "out of band" in message.lower()
