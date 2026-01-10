from datetime import UTC, datetime
import uuid


def get_datetime():
    return datetime.now(UTC)


def get_default_cash_balance():
    return 10_000

def gen_api_key():
    return str(uuid.uuid4())