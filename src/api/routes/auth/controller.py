import random
import string


def gen_verification_code(k: int = 6):
    """Generates a random verification code."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=k))
