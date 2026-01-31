import uuid

from sqlalchemy import UUID, Numeric
from sqlalchemy.orm import DeclarativeBase, mapped_column


def uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def balance_field(**kw):
    return mapped_column(
        Numeric(precision=12, scale=2, asdecimal=False), nullable=False, **kw
    )


class Base(DeclarativeBase):
    pass
