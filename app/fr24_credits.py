"""Provisional FR24 credit-cost constants from FLIGHTRADAR_API.md, pending confirmation against the operator's FR24 dashboard."""

from datetime import datetime, timezone

CATEGORY_ENUM = frozenset({"P", "C", "M", "J", "T", "H", "B", "G", "D", "V", "O", "N"})
DEFAULT_CATEGORIES = ("T", "H", "N")


def estimate_light_credits(returned_count: int) -> int:
    # 1 credit if the response was empty, else 6 credits per returned aircraft.
    # NEVER compute this as '1 + 6 * returned_count' -- that is a documented wrong formula.
    return 1 if returned_count == 0 else 6 * returned_count


def estimate_summary_full_credits(returned_count: int) -> int:
    return 2 * returned_count


def estimate_track_credits(returned_count: int) -> int:
    return 40 * returned_count


def all_empty_baseline(clusters: int, poll_interval_seconds: int, days: int = 30) -> int:
    # Number of live-position credits if every single poll returns an empty response.
    cycles = (days * 86400) // poll_interval_seconds
    return clusters * cycles


def monthly_credit_projection(
    total_calls: int, non_empty_fraction: float, avg_aircraft_per_nonempty: float
) -> float:
    # monthly_credits = N * (1 + p * (6r - 1))
    return total_calls * (1 + non_empty_fraction * (6 * avg_aircraft_per_nonempty - 1))


def projected_end_of_cycle_credits(credits_used: int, elapsed_fraction: float) -> float | None:
    # None means "insufficient data to project" -- callers must render that
    # explicitly (e.g. an "Insufficient data" dashboard status), never as 0
    # credits projected, which would read as maximum budget headroom.
    if elapsed_fraction <= 0:
        return None
    return credits_used / elapsed_fraction


def budget_state(credits_used: int, operating_budget: int) -> str:
    # Returns one of: 'normal', 'warning', 'critical', 'hard_limit', 'exhausted'
    if operating_budget <= 0:
        return "exhausted"
    fraction = credits_used / operating_budget
    if fraction >= 1.0:
        return "exhausted"
    if fraction >= 0.95:
        return "hard_limit"
    if fraction >= 0.85:
        return "critical"
    if fraction >= 0.70:
        return "warning"
    return "normal"


def billing_cycle_id(now: datetime) -> str:
    # Naive datetimes are assumed already UTC (matches detection.py's
    # parse_time() convention); aware datetimes are normalized to UTC so a
    # cycle boundary near local midnight doesn't drift onto the wrong month.
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc)
    return now.strftime("%Y-%m")
