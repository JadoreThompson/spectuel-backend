from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, field_validator

from api.exc import CustomValidationError
from models import CustomBaseModel


class PasswordField(BaseModel):
    password: str

    @field_validator("password", mode="before")
    def password_validator(cls, value: str) -> str:
        # min_length = 8
        # min_special_chars = 2
        # min_uppercase = 2
        # status = 400
        min_length = 2
        min_special_chars = 0
        min_uppercase = 0
        status = 400

        if len(value) < min_length:
            raise CustomValidationError(
                status, f"Password must be at least {min_length} characters long."
            )

        if sum(1 for c in value if c.isupper()) < min_uppercase:
            raise CustomValidationError(
                status,
                f"Password must contain at least {min_uppercase} uppercase letters.",
            )

        if sum(1 for c in value if not c.isalnum()) < min_special_chars:
            raise CustomValidationError(
                status,
                f"Password must contain at least {min_special_chars} special characters.",
            )

        return value


class UserCreate(PasswordField):
    username: str
    email: EmailStr


class UserLogin(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    password: str

    def model_post_init(self, context):
        if self.username is None and self.email is None:
            raise ValueError("Either email or username must be provided.")
        return self


class UserRead(BaseModel):
    username: str
    created_at: datetime


class UserMe(CustomBaseModel):
    username: str


class UpdateUsername(BaseModel):
    username: str


class UpdateEmail(BaseModel):
    email: EmailStr


class UpdatePassword(PasswordField):
    pass


class VerifyCode(BaseModel):
    code: str


class VerifyAction(VerifyCode):
    action: Literal["change_username", "change_password", "change_email"]


class WsTokenResponse(BaseModel):
    token: str