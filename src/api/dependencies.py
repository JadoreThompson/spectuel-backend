from typing import Callable, Type, TypeVar

from fastapi import Request, WebSocket
from fastapi.responses import JSONResponse

from config import COOKIE_ALIAS
from services import JWTService, ApiKeyService, KafkaService
from utils.db import smaker
from .exc import ApiKeyError, JWTError
from .typing import JWTPayload


T = TypeVar("T")


# async def depends_verify_jwt(req: Request) -> JWTPayload:
#     """Verify the JWT token from the request cookies and validate it.

#     Args:
#         req (Request)

#     Raises:
#         JWTError: If the JWT token is missing, expired, or invalid.

#     Returns:
#         JWTPayload: The decoded JWT payload if valid.
#     """
#     token = req.cookies.get(COOKIE_ALIAS)

#     if not token:
#         raise JWTError("JWT token is missing")

#     payload = JWTService.decode_jwt(token)
#     return await JWTService.validate_jwt(payload)


def depends_jwt(is_authenticated: bool = True):
    """Verify the JWT token from the request cookies and validate it."""

    async def func(req: Request) -> JWTPayload:
        """
        Args:
            req (Request)

        Raises:
            JWTError: If the JWT token is missing, expired, or invalid.

        Returns:
            JWTPayload: The decoded JWT payload if valid.
        """
        token = req.cookies.get(COOKIE_ALIAS)
        if not token:
            raise JWTError("Authentication token is missing")

        return await JWTService.validate_jwt(token, is_authenticated=is_authenticated)

    return func


async def depends_api_key_ws(ws: WebSocket) -> JWTPayload:
    api_key = ws.headers.get("Authorization")
    if not api_key:
        raise ApiKeyError("Api key is missing")
    return await ApiKeyService.validate_api_key(api_key)


def depends_convert_csv(
    param_name: str, target_type: Type[T], default: list[T] | None = None
) -> Callable[[Request], list[T]]:
    """Converts a query parameter from csv format to list[T]

    Args:
        param_name (str)
        target_type (Type[T]): Type for each item in list.
        default (list[T] | None, optional): Default value if param isn't passed.
            Defaults to None.
    """

    def wrapper(req: Request) -> list[T]:
        value = req.query_params.get(param_name)
        if not value:
            return default

        try:
            return [target_type(item.strip()) for item in value.strip().split(",")]
        except (ValueError, TypeError):
            raise JSONResponse(
                status_code=400, content={"error": f"Invalid {param_name}"}
            )

    return wrapper


async def depends_db_sess():
    async with smaker.begin() as db_sess:
        try:
            yield db_sess
        except:
            await db_sess.rollback()
            raise


async def depends_kafka_producer():
    return KafkaService.get_producer()
