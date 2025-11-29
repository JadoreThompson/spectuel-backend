import json

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import depends_jwt
from api.dependencies import depends_db_sess
from api.typing import JWTPayload
from config import (
    MAX_EMAIL_VERIFICATION_ATTEMPTS,
    PW_HASH_SALT,
    REDIS_CHANGE_EMAIL_KEY_PREFIX,
    REDIS_CHANGE_PASSWORD_KEY_PREFIX,
    REDIS_CHANGE_USERNAME_KEY_PREFIX,
    REDIS_EMAIL_VERIFICATION_KEY_PREFIX,
    REDIS_EMAIL_VERIFICATION_EXPIRY_SECS,
)
from db_models import Users
from services import JWTService, EmailService
from utils.redis import REDIS_CLIENT
from utils.utils import get_datetime
from .controller import gen_verification_code
from .models import (
    UpdateEmail,
    UpdatePassword,
    UpdateUsername,
    UserCreate,
    UserLogin,
    UserMe,
    VerifyAction,
    VerifyCode,
)


router = APIRouter(prefix="/auth", tags=["auth"])
em_service = EmailService("No-Reply", "no-reply@domain.com")
pw_hasher = PasswordHasher()


# @route.post("/login")
# async def login_user(
#     body: UserLogin, db_sess: AsyncSession = Depends(depends_db_sess)
# ):
#     query = select(Users)

#     if body.username is not None:
#         query = query.where(Users.username == body.username)
#     if body.email is not None:
#         query = query.where(Users.email == body.email)

#     user = await db_sess.scalar(query)
#     if user is None or user.password != body.password:
#         raise HTTPException(status_code=400, detail="Invalid credentials")

#     rsp = JSONResponse(content={"message": "Logged in successfully."})
#     return JWTService.set_cookie(user, rsp)


@router.post("/login")
async def login(body: UserLogin, db_sess: AsyncSession = Depends(depends_db_sess)):
    query = select(Users)

    if body.username is not None:
        query = query.where(Users.username == body.username)
    if body.email is not None:
        query = query.where(Users.email == body.email)

    user = await db_sess.scalar(query)
    if user is None:
        raise HTTPException(status_code=400, detail="User doesn't exist.")

    try:
        pw_hasher.verify(user.password, body.password)
    except Argon2Error:
        raise HTTPException(status_code=400, detail="Invalid password.")

    rsp = await JWTService.set_jwt_cookie_v2(user, db_sess)
    await db_sess.commit()
    return rsp


# @router.post("/register")
# async def register_user(
#     body: UserCreate, db_sess: AsyncSession = Depends(depends_db_sess)
# ):
#     result = await db_sess.execute(select(Users).where(Users.username == body.username))
#     if result.scalar_one_or_none():
#         return JSONResponse(
#             status_code=409, content={"error": "Username already registered"}
#         )

#     user = await db_sess.scalar(
#         insert(Users)
#         .values(username=body.username, email=body.email, password=body.password)
#         .returning(Users)
#     )

#     await db_sess.commit()

#     rsp = JSONResponse(status_code=200, content={"message": "Registered successfully."})
#     return JWTService.set_cookie(user, rsp)


@router.post("/register", status_code=202)
async def register(
    body: UserCreate,
    bg_tasks: BackgroundTasks,
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    global em_service
    global pw_hasher

    res = await db_sess.scalar(
        select(Users).where(
            (Users.username == body.username) | (Users.email == body.email)
        )
    )
    if res is not None:
        raise HTTPException(status_code=400, detail="Username or email already exists.")

    body.password = pw_hasher.hash(body.password, salt=PW_HASH_SALT.encode())

    user = await db_sess.scalar(
        insert(Users).values(**body.model_dump()).returning(Users)
    )

    code = gen_verification_code()
    key = f"{REDIS_EMAIL_VERIFICATION_KEY_PREFIX}{str(user.user_id)}"
    await REDIS_CLIENT.delete(key)
    payload = {"code": code, "attempts": 0}
    await REDIS_CLIENT.set(
        key, json.dumps(payload), ex=REDIS_EMAIL_VERIFICATION_EXPIRY_SECS
    )

    bg_tasks.add_task(
        em_service.send_email,
        body.email,
        "Verify your email",
        f"Your verification code is: {code}",
    )

    rsp = await JWTService.set_jwt_cookie_v2(user, db_sess)
    await db_sess.commit()

    return rsp


@router.post("/request-email-verification")
async def request_email_verification(
    bg_tasks: BackgroundTasks, jwt: JWTPayload = Depends(depends_jwt(False))
):
    global em_service

    new_code = gen_verification_code()
    key = f"{REDIS_EMAIL_VERIFICATION_KEY_PREFIX}{str(jwt.sub)}"
    payload = await REDIS_CLIENT.get(key)

    if payload:
        payload = json.loads(payload)
    else:
        payload = {"attempts": 0, "code": None}

    if payload["attempts"] + 1 > MAX_EMAIL_VERIFICATION_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Max attempts reached")

    payload["attempts"] += 1
    payload["code"] = new_code

    await REDIS_CLIENT.delete(key)
    await REDIS_CLIENT.set(
        key, json.dumps(payload), ex=REDIS_EMAIL_VERIFICATION_EXPIRY_SECS
    )

    bg_tasks.add_task(
        em_service.send_email,
        jwt.em,
        "Verify your email",
        f"Your verification code is: {new_code}",
    )


@router.post("/verify-email")
async def verify_email(
    body: VerifyCode,
    jwt: JWTPayload = Depends(depends_jwt(False)),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    key = f"{REDIS_EMAIL_VERIFICATION_KEY_PREFIX}{str(jwt.sub)}"
    # code = await REDIS_CLIENT.get(key)
    payload = await REDIS_CLIENT.get(key)
    if not payload:
        raise HTTPException(status_code=400, detail="No code found")
    
    code = payload["code"]
    await REDIS_CLIENT.delete(key)

    if code is None or code != body.code:
        raise HTTPException(
            status_code=400, detail="Invalid or expired verification code."
        )

    user = await db_sess.scalar(select(Users).where(Users.user_id == jwt.sub))
    user.authenticated_at = get_datetime()
    rsp = await JWTService.set_jwt_cookie_v2(user, db_sess)
    await db_sess.commit()
    return rsp


@router.post("/logout")
async def logout(
    jwt: JWTPayload = Depends(depends_jwt(True)),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    rsp = JWTService.remove_jwt()
    await db_sess.execute(
        update(Users).values(jwt=None).where(Users.user_id == jwt.sub)
    )
    await db_sess.commit()
    return rsp


@router.get("/me", response_model=UserMe)
async def get_me(
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    user = await db_sess.scalar(select(Users).where(Users.user_id == jwt.sub))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    return UserMe(username=user.username)


@router.post("/change-username", status_code=202)
async def change_username(
    body: UpdateUsername,
    bg_tasks: BackgroundTasks,
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    global em_service

    user = await db_sess.scalar(select(Users).where(Users.user_id == jwt.sub))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    existing_user = await db_sess.scalar(
        select(Users).where(Users.username == body.username)
    )
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists.")

    prefix = f"{REDIS_CHANGE_USERNAME_KEY_PREFIX}{jwt.sub}:"
    async for key in REDIS_CLIENT.scan_iter(f"{prefix}*"):
        await REDIS_CLIENT.delete(key)

    verification_code = gen_verification_code()
    payload = json.dumps(
        {
            "user_id": str(user.user_id),
            "action": "change_username",
            "new_value": body.username,
        }
    )
    redis_key = f"{prefix}{verification_code}"
    await REDIS_CLIENT.set(
        redis_key, json.dumps(payload), ex=REDIS_EMAIL_VERIFICATION_EXPIRY_SECS
    )

    bg_tasks.add_task(
        em_service.send_email,
        user.email,
        "Confirm Your Username Change",
        f"Your verification code is: {verification_code}",
    )

    return {"message": "A verification code has been sent to your email."}


@router.post("/change-username", status_code=202)
async def change_username(
    body: UpdateEmail,
    bg_tasks: BackgroundTasks,
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    global em_service

    user = await db_sess.scalar(select(Users).where(Users.user_id == jwt.sub))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    existing_user = await db_sess.scalar(select(Users).where(Users.email == body.email))
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists.")

    prefix = f"{REDIS_CHANGE_EMAIL_KEY_PREFIX}{jwt.sub}:"
    async for key in REDIS_CLIENT.scan_iter(f"{prefix}*"):
        await REDIS_CLIENT.delete(key)

    verification_code = gen_verification_code()
    payload = json.dumps(
        {
            "user_id": str(user.user_id),
            "action": "change_email",
            "new_value": body.email,
        }
    )
    redis_key = f"{prefix}{verification_code}"
    await REDIS_CLIENT.set(
        redis_key, json.dumps(payload), ex=REDIS_EMAIL_VERIFICATION_EXPIRY_SECS
    )

    bg_tasks.add_task(
        em_service.send_email,
        user.email,
        "Confirm Your Email Change",
        f"Your verification code is: {verification_code}",
    )

    return {"message": "A verification code has been sent to your email."}


@router.post("/change-password", status_code=202)
async def change_password(
    body: UpdatePassword,
    bg_tasks: BackgroundTasks,
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    global em_service

    user = await db_sess.scalar(select(Users).where(Users.user_id == jwt.sub))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    prefix = f"{REDIS_CHANGE_PASSWORD_KEY_PREFIX}{jwt.sub}"
    async for key in REDIS_CLIENT.scan_iter(f"{prefix}*"):
        await REDIS_CLIENT.delete(key)

    verification_code = gen_verification_code()

    payload = json.dumps(
        {
            "user_id": str(user.user_id),
            "action": "change_password",
            "new_value": body.password,
        }
    )

    await REDIS_CLIENT.set(
        f"{prefix}{verification_code}",
        payload,
        ex=REDIS_EMAIL_VERIFICATION_EXPIRY_SECS,
    )

    bg_tasks.add_task(
        em_service.send_email,
        user.email,
        "Confirm Your Password Change",
        f"Your verification code is: {verification_code}",
    )

    return {"message": "A verification code has been sent to your email."}


@router.post("/verify-action")
async def verify_action(
    body: VerifyAction,
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    global pw_hasher

    redis_key = f"{body.action}:{jwt.sub}:{body.code}"
    data_str = await REDIS_CLIENT.get(redis_key)
    if not data_str:
        raise HTTPException(
            status_code=400, detail="Invalid or expired verification code."
        )

    await REDIS_CLIENT.delete(redis_key)

    data = json.loads(data_str)
    user_id = data["user_id"]
    if user_id != jwt.sub:
        raise HTTPException(status_code=401, detail="Unauthorised request.")

    action = data["action"]
    new_value = data["new_value"]

    if action == "change_username":
        existing_user = await db_sess.scalar(
            select(Users).where(Users.username == new_value)
        )
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already taken.")

        await db_sess.execute(
            update(Users).where(Users.user_id == user_id).values(username=new_value)
        )
        message = "Username changed successfully."
        await db_sess.commit()
        return {"message": message}

    if action == "change_email":
        await db_sess.execute(
            update(Users).where(Users.user_id == user_id).values(emailassword=new_value)
        )
        await db_sess.execute(
            update(Users).values(jwt=None).where(Users.user_id == user_id)
        )
        rsp = JWTService.remove_jwt()
        await db_sess.commit()
        return rsp

    if action == "change_password":
        await db_sess.execute(
            update(Users)
            .where(Users.user_id == user_id)
            .values(password=pw_hasher.hash(new_value, salt=PW_HASH_SALT.encode()))
        )

        await db_sess.execute(
            update(Users).values(jwt=None).where(Users.user_id == user_id)
        )

        rsp = JSONResponse(
            status_code=200, content={"message": "Password changed successfully."}
        )
        rsp = JWTService.remove_jwt(rsp)
        await db_sess.commit()
        return rsp

    raise HTTPException(status_code=400, detail="Unknown action specified.")
