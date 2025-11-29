from datetime import UTC, datetime


def get_datetime():
    return datetime.now(UTC)


def get_default_cash_balance():
    return 10_000
