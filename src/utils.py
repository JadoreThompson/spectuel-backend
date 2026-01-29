import random
import string
import uuid
from datetime import UTC, datetime


def get_datetime():
    return datetime.now(UTC)


def get_default_cash_balance():
    return 10_000

def gen_api_key():
    return str(uuid.uuid4())

def gen_random_string(k: int = 6):
    """Generates a random string."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=k))