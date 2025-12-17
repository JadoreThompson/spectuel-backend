from engine.config import SYSTEM_USER_ID


def ignore_system_user(func):
    def wrapper(self, user_id: str, *args, **kw):
        if user_id == SYSTEM_USER_ID:
            return
        return func(self, user_id, *args, **kw)

    return wrapper