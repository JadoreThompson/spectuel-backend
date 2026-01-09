from engine.config import SYSTEM_USER_ID


def ignore_system_user(func):
    """
    A decorator which mutes the called function
    if the user id is the SYSTEM_USER_ID. The user_id
    param must be a position param in the first position.
    """
    def wrapper(self, user_id: str, *args, **kw):
        if user_id == SYSTEM_USER_ID:
            return
        return func(self, user_id, *args, **kw)

    return wrapper