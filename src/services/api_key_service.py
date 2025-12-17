import secrets
import string
from datetime import datetime

from sqlalchemy import select

from api.exc import ApiKeyError
from api.types import JWTPayload
from db_models import Users
from utils.db import get_db_sess


class ApiKeyService:
    @staticmethod
    def generate_api_key(length: int = 40) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    async def validate_api_key(api_key: str) -> JWTPayload:
        async with get_db_sess() as db_sess:
            user = await db_sess.scalar(select(Users).where(Users.api_key == api_key))
            if user is None:
                raise ApiKeyError("Invalid api key")
            return JWTPayload(sub=user.user_id, exp=datetime.now())
