from datetime import datetime

from models import CustomBaseModel


class JWTPayload(CustomBaseModel):
    sub: str  # user id
    em: str
    exp: datetime
    authenticated: bool
