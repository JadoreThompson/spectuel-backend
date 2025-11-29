from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import depends_verify_jwt
from api.dependencies import depends_db_sess
from api.services import JWTService
from api.typing import JWTPayload
from db_models import Users
from .models import UserCreate, UserLogin


route = APIRouter(prefix="/auth", tags=["auth"])


@route.post("/login")
async def login_user(
    body: UserLogin, db_sess: AsyncSession = Depends(depends_db_sess)
):
    query = select(Users)

    if body.username is not None:
        query = query.where(Users.username == body.username)
    if body.email is not None:
        query = query.where(Users.email == body.email)

    user = await db_sess.scalar(query)
    if user is None or user.password != body.password:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    
    rsp = JSONResponse(content={"message": "Logged in successfully."})
    return JWTService.set_cookie(user, rsp)


@route.post("/register")
async def register_user(
    body: UserCreate, db_sess: AsyncSession = Depends(depends_db_sess)
):
    result = await db_sess.execute(select(Users).where(Users.username == body.username))
    if result.scalar_one_or_none():
        return JSONResponse(
            status_code=409, content={"error": "Username already registered"}
        )

    user = await db_sess.scalar(
        insert(Users)
        .values(username=body.username, email=body.email, password=body.password)
        .returning(Users)
    )

    await db_sess.commit()

    rsp = JSONResponse(status_code=200, content={"message": "Registered successfully."})
    return JWTService.set_cookie(user, rsp)


@route.get("/me")
async def get_current_user(jwt_payload: JWTPayload = Depends(depends_verify_jwt)):
    pass
