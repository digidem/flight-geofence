from datetime import datetime, timedelta, timezone

from app.fr24_credits import (
    all_empty_baseline,
    billing_cycle_id,
    budget_state,
    estimate_light_credits,
    estimate_summary_full_credits,
    estimate_track_credits,
    monthly_credit_projection,
    projected_end_of_cycle_credits,
)


def test_estimate_light_credits_empty():
    assert estimate_light_credits(0) == 1


def test_estimate_light_credits_one():
    assert estimate_light_credits(1) == 6


def test_estimate_light_credits_five():
    assert estimate_light_credits(5) == 30


def test_estimate_light_credits_not_wrong_formula():
    # Guards against the documented wrong formula `1 + 6*n`.
    assert estimate_light_credits(3) == 18


def test_estimate_summary_full_credits():
    assert estimate_summary_full_credits(4) == 8


def test_estimate_track_credits():
    assert estimate_track_credits(2) == 80


def test_all_empty_baseline():
    assert all_empty_baseline(clusters=2, poll_interval_seconds=300, days=30) == 17280


def test_monthly_credit_projection_all_empty():
    assert (
        monthly_credit_projection(
            total_calls=17280, non_empty_fraction=0.0, avg_aircraft_per_nonempty=1.0
        )
        == 17280.0
    )


def test_monthly_credit_projection_all_nonempty():
    assert (
        monthly_credit_projection(
            total_calls=17280, non_empty_fraction=1.0, avg_aircraft_per_nonempty=1.0
        )
        == 17280.0 * 6
    )


def test_projected_end_of_cycle_credits_half():
    assert projected_end_of_cycle_credits(credits_used=10000, elapsed_fraction=0.5) == 20000.0


def test_projected_end_of_cycle_credits_insufficient_data():
    # elapsed_fraction<=0 means "not enough data yet", not "zero projected" --
    # 0.0 would render as false confidence on a viability dashboard.
    assert projected_end_of_cycle_credits(credits_used=10000, elapsed_fraction=0) is None


def test_budget_state_normal():
    assert budget_state(credits_used=1000, operating_budget=28000) == "normal"


def test_budget_state_warning():
    assert budget_state(credits_used=20000, operating_budget=28000) == "warning"


def test_budget_state_critical():
    assert budget_state(credits_used=25000, operating_budget=28000) == "critical"


def test_budget_state_hard_limit():
    assert budget_state(credits_used=27000, operating_budget=28000) == "hard_limit"


def test_budget_state_exhausted():
    assert budget_state(credits_used=28000, operating_budget=28000) == "exhausted"


def test_billing_cycle_id():
    assert billing_cycle_id(datetime(2026, 7, 25)) == "2026-07"


def test_billing_cycle_id_normalizes_aware_datetime_to_utc():
    # 23:00 on July 31 in UTC-3 is 02:00 UTC on August 1 -- must land in August,
    # not silently stay in July because of a naive local-time comparison.
    late_local = datetime(2026, 7, 31, 23, 0, tzinfo=timezone(timedelta(hours=-3)))
    assert billing_cycle_id(late_local) == "2026-08"
