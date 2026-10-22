"""Tests for parsing NGED power cut records and working out what affects you."""

from datetime import UTC, datetime

import pytest

from custom_components.nged_power_cuts.models import (
    diff_cuts,
    normalise_postcode,
    parse_nged_time,
    parse_power_cuts,
    summarise,
)
from tests.conftest import LAT, LON, POSTCODE, live_records

NOW = datetime(2026, 10, 22, 21, 30, tzinfo=UTC)


def record(**changes):
    """A real in-progress fault from the feed, with some fields changed."""
    base = next(r for r in live_records() if r["fault_id"] == "INCD-109435-l")
    base.update(changes)
    return base


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("NP25 3PL", "NP25 3PL"),
        ("np253pl", "NP25 3PL"),
        ("  np25  3pl ", "NP25 3PL"),
        ("SW1A 1AA", "SW1A 1AA"),
        ("B1 1AA", "B1 1AA"),
        ("M60 1NW", "M60 1NW"),
        ("CR2 6XH", "CR2 6XH"),
        ("DN55 1PT", "DN55 1PT"),
        ("not a postcode", None),
        ("NP25", None),
        ("", None),
        (None, None),
    ],
)
def test_normalise_postcode(value, expected) -> None:
    assert normalise_postcode(value) == expected


def test_times_are_uk_local() -> None:
    # Summer time: 22:31 in the feed is 21:31 UTC.
    assert parse_nged_time("2026-10-22T22:31:00") == datetime(
        2026, 10, 22, 21, 31, tzinfo=UTC
    )
    # Winter time: the same as UTC.
    assert parse_nged_time("2027-01-22T12:00:00") == datetime(
        2027, 1, 22, 12, 0, tzinfo=UTC
    )
    assert parse_nged_time("") is None
    assert parse_nged_time(None) is None
    assert parse_nged_time("not a time") is None


def test_parse_live_feed() -> None:
    cuts = parse_power_cuts(live_records())
    assert len(cuts) == 13

    cardiff = next(c for c in cuts if c.id == "INCD-7034-j")
    assert cardiff.planned
    assert cardiff.area == "South Wales"
    assert cardiff.category == "HV PLANNED"
    assert cardiff.postcodes == frozenset({"CF10 4RP"})
    assert cardiff.planned_start == datetime(2026, 7, 22, 11, 0, tzinfo=UTC)
    assert cardiff.planned_end == datetime(2027, 1, 22, 12, 0, tzinfo=UTC)
    assert cardiff.active

    fault = next(c for c in cuts if c.id == "INCD-109435-l")
    assert not fault.planned
    assert fault.psr_customers == 34
    assert fault.estimated_restoration == datetime(2026, 10, 22, 23, 0, tzinfo=UTC)
    assert "TR5 0PY" in fault.postcodes


def test_records_without_an_id_are_skipped() -> None:
    assert parse_power_cuts([record(fault_id=""), {"unexpected": True}, "x"]) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"planned": "true"},
        {"category": "LV PLANNED"},
        {"planned_outage_start_date": "2026-11-01T09:00:00"},
    ],
)
def test_planned_is_recognised_any_way_the_feed_marks_it(changes) -> None:
    (cut,) = parse_power_cuts([record(**changes)])
    assert cut.planned


@pytest.mark.parametrize(
    "changes",
    [
        {"date_of_restoration": "2026-10-22T22:00:00"},
        {"status": "Restored"},
        {"status": "Completed"},
    ],
)
def test_restored_cuts_are_not_active(changes) -> None:
    (cut,) = parse_power_cuts([record(**changes)])
    assert not cut.active


def test_distance() -> None:
    (cut,) = parse_power_cuts([record()])
    # The fault is near Truro, about 188 km from Cardiff as the crow flies.
    assert 180 < cut.distance_km(LAT, LON) < 200
    (no_location,) = parse_power_cuts([record(location_latitude=None)])
    assert no_location.distance_km(LAT, LON) is None


def test_summarise_your_postcode_and_nearby() -> None:
    near = record(
        fault_id="NEAR",
        postcode="CF10 1AA",
        location_latitude=LAT + 0.01,
        location_longitude=LON,
    )
    data = summarise(
        parse_power_cuts([*live_records(), near]), POSTCODE, LAT, LON, 5, NOW
    )

    assert [c.id for c in data.yours] == ["INCD-7034-j"]
    assert [(c.id, round(d)) for c, d in data.nearby] == [
        ("INCD-7034-j", 0),
        ("NEAR", 1),
    ]
    assert [c.id for c in data.planned] == ["INCD-7034-j"]
    assert {c.id for c in data.relevant} == {"INCD-7034-j", "NEAR"}


def test_planned_work_that_has_not_started_is_not_a_power_cut_yet() -> None:
    future = record(
        fault_id="FUTURE",
        postcode=POSTCODE,
        planned="true",
        category="LV PLANNED",
        planned_outage_start_date="2026-10-25T12:00:00",
    )
    data = summarise(parse_power_cuts([future]), POSTCODE, LAT, LON, 5, NOW)

    assert data.yours == []
    assert data.nearby == []
    assert [c.id for c in data.planned] == ["FUTURE"]
    assert [c.id for c in data.relevant] == ["FUTURE"]


def test_restored_cuts_drop_out_of_the_summary() -> None:
    restored = record(postcode=POSTCODE, date_of_restoration="2026-10-22T22:00:00")
    data = summarise(parse_power_cuts([restored]), POSTCODE, LAT, LON, 5, NOW)
    assert data.yours == []
    assert data.relevant == []


def test_diff_cuts() -> None:
    before_records = [record(fault_id="A"), record(fault_id="B")]
    before = {c.id: c for c in parse_power_cuts(before_records)}
    after_records = [
        record(fault_id="A", etr="2026-10-23T03:00:00"),  # restoration time moved
        record(fault_id="C"),  # new
    ]
    after = {c.id: c for c in parse_power_cuts(after_records)}

    changes = sorted((change, cut.id) for change, cut in diff_cuts(before, after))

    assert changes == [("new", "C"), ("restored", "B"), ("updated", "A")]
    assert diff_cuts(after, after) == []


def test_as_dict_for_attributes() -> None:
    (cut,) = parse_power_cuts([record()])
    info = cut.as_dict(distance_km=12.345)
    assert info["id"] == "INCD-109435-l"
    assert info["estimated_restoration"] == "2026-10-22T23:00:00+00:00"
    assert info["distance_km"] == 12.3
    assert info["planned"] is False
    assert isinstance(info["postcodes"], list)
