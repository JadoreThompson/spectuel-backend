from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str


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
