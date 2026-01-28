from fastapi.responses import JSONResponse
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timedelta
import json
from argon2 import PasswordHasher
import pytest_asyncio

from api.app import app
from api.dependencies import depends_db_sess
from api.types import JWTPayload
from db_models import Users
from config import (
    COOKIE_ALIAS,
    PW_HASH_SALT,
    REDIS_EMAIL_VERIFICATION_KEY_PREFIX,
    REDIS_EMAIL_VERIFICATION_EXPIRY_SECS,
    REDIS_CHANGE_USERNAME_KEY_PREFIX,
    REDIS_CHANGE_EMAIL_KEY_PREFIX,
    REDIS_CHANGE_PASSWORD_KEY_PREFIX,
    MAX_EMAIL_VERIFICATION_ATTEMPTS,
    NEW_USER_COMMAND_ID
)
from services import JWTService, EmailService
from utils import get_datetime, get_default_cash_balance

# Mock data
TEST_USER_ID = str(uuid4())
TEST_EMAIL = "test@example.com"
TEST_USERNAME = "testuser"
TEST_PASSWORD = "TestPassword1!"
NEW_USERNAME = "newtestuser"
NEW_EMAIL = "new@example.com"
NEW_PASSWORD = "NewPassword1!"


@pytest.fixture
def mock_jwt_payload():
    return JWTPayload(
        sub=TEST_USER_ID,
        exp=int((get_datetime() + timedelta(days=1)).timestamp()),
        em=TEST_EMAIL,
        authenticated=True,
    )


@pytest.fixture
def mock_jwt_payload_unauthenticated():
    return JWTPayload(
        sub=TEST_USER_ID,
        exp=int((get_datetime() + timedelta(days=1)).timestamp()),
        em=TEST_EMAIL,
        authenticated=False,
    )


@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    # Mock execute result for list queries
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar.return_value = None  # Default for scalar, can be overridden
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    session.get.return_value = None
    return session


@pytest.fixture
def mock_redis_client():
    with patch("api.routers.auth.router.REDIS_CLIENT", new_callable=AsyncMock) as mock_redis:
        # Mock scan_iter to yield nothing by default
        mock_redis.scan_iter.return_value.__aiter__.return_value = iter([])
        yield mock_redis


@pytest.fixture
def mock_email_service():
    with patch("api.routers.auth.router.EmailService", autospec=True) as mock_service_cls:
        mock_instance = mock_service_cls.return_value
        mock_instance.send_email = AsyncMock()
        yield mock_instance


@pytest.fixture
def mock_balance_manager():
    with patch("api.routers.auth.router.BalanceManager", autospec=True) as mock_manager_cls:
        mock_instance = mock_manager_cls.return_value
        mock_instance.increase_cash_balance_async = AsyncMock()
        yield mock_instance


@pytest_asyncio.fixture
async def client(
    mock_jwt_payload,
    mock_jwt_payload_unauthenticated,
    mock_db_session,
    mock_redis_client,
    mock_email_service,
    mock_balance_manager,
):
    # Override DB dependency
    async def override_db_sess():
        yield mock_db_session

    app.dependency_overrides[depends_db_sess] = override_db_sess

    # Mock JWT validation
    mock_validate_jwt_authenticated = AsyncMock(return_value=mock_jwt_payload)
    mock_validate_jwt_unauthenticated = AsyncMock(return_value=mock_jwt_payload_unauthenticated)

    with patch(
        "services.jwt_service.JWTService.validate_jwt", new_callable=MagicMock
    ) as mock_validate_jwt_service:
        # Configure validate_jwt to return different payloads based on is_authenticated
        def side_effect_jwt_validate(token, is_authenticated):
            if is_authenticated:
                return mock_validate_jwt_authenticated(token, is_authenticated)
            else:
                return mock_validate_jwt_unauthenticated(token, is_authenticated)

        mock_validate_jwt_service.side_effect = side_effect_jwt_validate

        # Mock JWTService.set_persistant_jwt_cookie and remove_jwt
        with patch("services.jwt_service.JWTService.set_persistant_jwt_cookie", new_callable=AsyncMock) as mock_set_cookie:
            mock_set_cookie.return_value = JSONResponse(
                content={"message": "Logged in"},
                headers={"Set-Cookie": f"{COOKIE_ALIAS}=test_jwt_token; Path=/; HttpOnly; SameSite=lax"},
            )
            with patch("services.jwt_service.JWTService.remove_jwt", new_callable=MagicMock) as mock_remove_jwt:
                mock_remove_jwt.return_value = JSONResponse(
                    content={"message": "Logged out"},
                    headers={"Set-Cookie": f"{COOKIE_ALIAS}=; Path=/; HttpOnly; SameSite=lax; Expires=Thu, 01 Jan 1970 00:00:00 GMT"},
                )
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    ac.cookies = {COOKIE_ALIAS: "valid_token"}
                    yield ac, mock_db_session, mock_redis_client, mock_email_service, mock_balance_manager, mock_set_cookie, mock_remove_jwt

    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_register_success(client):
    ac, db_sess, mock_redis_client, mock_email_service, _, mock_set_cookie, _ = client

    # Mock DB response for no existing user
    db_sess.scalar.return_value = None

    # Mock the return of the new user object after insertion
    mock_user = Users(
        user_id=uuid4(),
        username=TEST_USERNAME,
        email=TEST_EMAIL,
        password=PasswordHasher().hash(TEST_PASSWORD, salt=PW_HASH_SALT.encode()),
        created_at=get_datetime(),
        authenticated_at=None,
        jwt=None,
    )
    db_sess.scalar.side_effect = [None, mock_user] # First call for select, second for insert

    payload = {
        "username": TEST_USERNAME,
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
    }

    response = await ac.post("/auth/register", json=payload)
    assert response.status_code == 202
    assert "Set-Cookie" in response.headers
    assert mock_set_cookie.called_once

    # Verify DB interactions
    assert db_sess.scalar.call_count == 2
    assert db_sess.commit.called_once()

    # Verify Redis interactions
    mock_redis_client.delete.assert_called_once()
    mock_redis_client.set.assert_called_once()
    redis_key, redis_value_str, ex = mock_redis_client.set.call_args[0]
    assert redis_key.startswith(REDIS_EMAIL_VERIFICATION_KEY_PREFIX)
    redis_payload = json.loads(redis_value_str)
    assert "code" in redis_payload
    assert redis_payload["attempts"] == 0
    assert ex == REDIS_EMAIL_VERIFICATION_EXPIRY_SECS

    # Verify email service interaction
    mock_email_service.send_email.assert_called_once()
    args, _ = mock_email_service.send_email.call_args
    assert args[0] == TEST_EMAIL
    assert "Your verification code is:" in args[2]


@pytest.mark.asyncio
async def test_register_username_or_email_exists(client):
    ac, db_sess, _, _, _, _, _ = client

    # Mock DB response for an existing user
    db_sess.scalar.return_value = Users(
        user_id=uuid4(),
        username=TEST_USERNAME,
        email="other@example.com",
        password="",
        created_at=get_datetime(),
    )

    payload = {
        "username": TEST_USERNAME,
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
    }

    response = await ac.post("/auth/register", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Username or email already exists."
    db_sess.commit.assert_not_called()


@pytest.mark.asyncio
async def test_login_success(client):
    ac, db_sess, _, _, _, mock_set_cookie, _ = client

    ph = PasswordHasher()
    hashed_password = ph.hash(TEST_PASSWORD)

    # Mock DB response for existing user
    mock_user = Users(
        user_id=uuid4(),
        username=TEST_USERNAME,
        email=TEST_EMAIL,
        password=hashed_password,
        created_at=get_datetime(),
        authenticated_at=get_datetime(),
        jwt=None,
    )
    db_sess.scalar.return_value = mock_user

    payload = {"username": TEST_USERNAME, "password": TEST_PASSWORD}

    with patch("api.routers.auth.router.pw_hasher.verify", return_value=None):
        response = await ac.post("/auth/login", json=payload)
        assert response.status_code == 200
        assert "Set-Cookie" in response.headers
        mock_set_cookie.assert_called_once_with(mock_user, db_sess)
        db_sess.commit.assert_called_once()


@pytest.mark.asyncio
async def test_login_user_not_found(client):
    ac, db_sess, _, _, _, _, _ = client
    db_sess.scalar.return_value = None

    payload = {"username": TEST_USERNAME, "password": TEST_PASSWORD}
    response = await ac.post("/auth/login", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "User doesn't exist."


@pytest.mark.asyncio
async def test_login_invalid_password(client):
    ac, db_sess, _, _, _, _, _ = client

    ph = PasswordHasher()
    hashed_password = ph.hash("wrongpassword")

    mock_user = Users(
        user_id=uuid4(),
        username=TEST_USERNAME,
        email=TEST_EMAIL,
        password=hashed_password,
        created_at=get_datetime(),
    )
    db_sess.scalar.return_value = mock_user

    payload = {"username": TEST_USERNAME, "password": TEST_PASSWORD}

    with patch(
        "api.routers.auth.router.pw_hasher.verify",
        side_effect=lambda pw, h: ph.verify(pw, h),
    ) as mock_verify:
        response = await ac.post("/auth/login", json=payload)
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid password."
        mock_verify.assert_called_once()
    db_sess.commit.assert_not_called()


@pytest.mark.asyncio
async def test_request_email_verification_success(client):
    ac, _, mock_redis_client, mock_email_service, _, _, _ = client

    # Mock Redis to return no existing payload
    mock_redis_client.get.return_value = None

    response = await ac.post("/auth/request-email-verification")
    assert response.status_code == 200
    assert response.json() == {"message": "Verification email sent."}

    mock_redis_client.set.assert_called_once()
    redis_key, redis_value_str, ex = mock_redis_client.set.call_args[0]
    assert redis_key == f"{REDIS_EMAIL_VERIFICATION_KEY_PREFIX}{TEST_USER_ID}"
    redis_payload = json.loads(redis_value_str)
    assert redis_payload["attempts"] == 1
    assert "code" in redis_payload
    assert ex == REDIS_EMAIL_VERIFICATION_EXPIRY_SECS

    mock_email_service.send_email.assert_called_once()
    args, _ = mock_email_service.send_email.call_args
    assert args[0] == TEST_EMAIL
    assert "Your verification code is:" in args[2]


@pytest.mark.asyncio
async def test_request_email_verification_max_attempts(client):
    ac, _, mock_redis_client, _, _, _, _ = client

    # Mock Redis to return payload with max attempts
    mock_redis_client.get.return_value = json.dumps(
        {"attempts": MAX_EMAIL_VERIFICATION_ATTEMPTS, "code": "123456"}
    )

    response = await ac.post("/auth/request-email-verification")
    assert response.status_code == 400
    assert response.json()["detail"] == "Max attempts reached"

    mock_redis_client.set.assert_not_called()
    mock_redis_client.delete.assert_not_called()


@pytest.mark.asyncio
async def test_verify_email_success(client):
    ac, db_sess, mock_redis_client, _, mock_balance_manager, mock_set_cookie, _ = client

    verification_code = "123456"
    mock_redis_client.get.return_value = json.dumps(
        {"code": verification_code, "attempts": 1}
    )

    mock_user = Users(
        user_id=uuid4(TEST_USER_ID),  # ensure user_id matches jwt.sub
        username=TEST_USERNAME,
        email=TEST_EMAIL,
        password="hashed_pw",
        created_at=get_datetime(),
        authenticated_at=None,
    )
    db_sess.scalar.return_value = mock_user

    payload = {"code": verification_code}
    response = await ac.post("/auth/verify-email", json=payload)

    assert response.status_code == 200
    assert "Set-Cookie" in response.headers
    mock_set_cookie.assert_called_once_with(mock_user, db_sess)
    assert mock_user.authenticated_at is not None  # Verify timestamp was set
    mock_balance_manager.increase_cash_balance_async.assert_called_once_with(
        uuid4(TEST_USER_ID), get_default_cash_balance(), NEW_USER_COMMAND_ID
    )
    db_sess.commit.assert_called_once()
    mock_redis_client.delete.assert_called_once()


@pytest.mark.asyncio
async def test_verify_email_no_code_found(client):
    ac, _, mock_redis_client, _, _, _, _ = client
    mock_redis_client.get.return_value = None

    payload = {"code": "123456"}
    response = await ac.post("/auth/verify-email", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "No code found"


@pytest.mark.asyncio
async def test_verify_email_invalid_code(client):
    ac, _, mock_redis_client, _, _, _, _ = client
    mock_redis_client.get.return_value = json.dumps(
        {"code": "wrongcode", "attempts": 1}
    )

    payload = {"code": "123456"}
    response = await ac.post("/auth/verify-email", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired verification code."
    mock_redis_client.delete.assert_called_once() # code is deleted even if invalid


@pytest.mark.asyncio
async def test_logout_success(client):
    ac, db_sess, _, _, _, _, mock_remove_jwt = client

    # Mock the execute call for update
    db_sess.execute.return_value.rowcount = 1  # Indicate a row was updated

    response = await ac.post("/auth/logout")
    assert response.status_code == 200
    assert "Set-Cookie" in response.headers # JWT removal cookie
    mock_remove_jwt.assert_called_once()
    db_sess.execute.assert_called_once()
    db_sess.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_me_success(client, mock_jwt_payload):
    ac, db_sess, _, _, _, _, _ = client

    mock_user = Users(
        user_id=uuid4(TEST_USER_ID),
        username=TEST_USERNAME,
        email=TEST_EMAIL,
        password="hashed_pw",
        created_at=get_datetime(),
        authenticated_at=get_datetime(),
    )
    db_sess.scalar.return_value = mock_user

    response = await ac.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["username"] == TEST_USERNAME
    db_sess.scalar.assert_called_once()


@pytest.mark.asyncio
async def test_get_me_user_not_found(client):
    ac, db_sess, _, _, _, _, _ = client
    db_sess.scalar.return_value = None

    response = await ac.get("/auth/me")
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."


@pytest.mark.asyncio
async def test_change_username_request_success(client):
    ac, db_sess, mock_redis_client, mock_email_service, _, _, _ = client

    mock_user = Users(
        user_id=uuid4(TEST_USER_ID),
        username=TEST_USERNAME,
        email=TEST_EMAIL,
        password="hashed_pw",
        created_at=get_datetime(),
    )
    db_sess.scalar.side_effect = [mock_user, None]  # First for current user, second for new username existence

    response = await ac.post("/auth/change-username", json={"username": NEW_USERNAME})
    assert response.status_code == 202
    assert response.json()["message"] == "A verification code has been sent to your email."

    mock_redis_client.scan_iter.assert_called_once()
    mock_redis_client.set.assert_called_once()
    redis_key, redis_value_str, ex = mock_redis_client.set.call_args[0]
    assert redis_key.startswith(f"{REDIS_CHANGE_USERNAME_KEY_PREFIX}{TEST_USER_ID}:")
    redis_payload = json.loads(redis_value_str)
    assert redis_payload["action"] == "change_username"
    assert redis_payload["new_value"] == NEW_USERNAME

    mock_email_service.send_email.assert_called_once()
    args, _ = mock_email_service.send_email.call_args
    assert args[0] == TEST_EMAIL
    assert "Confirm Your Username Change" in args[1]
    assert "Your verification code is:" in args[2]


@pytest.mark.asyncio
async def test_change_username_user_not_found(client):
    ac, db_sess, _, _, _, _, _ = client
    db_sess.scalar.return_value = None

    response = await ac.post("/auth/change-username", json={"username": NEW_USERNAME})
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_change_username_already_exists(client):
    ac, db_sess, _, _, _, _, _ = client

    mock_user_current = Users(
        user_id=uuid4(TEST_USER_ID),
        username=TEST_USERNAME,
        email=TEST_EMAIL,
        password="hashed_pw",
        created_at=get_datetime(),
    )
    mock_user_existing = Users(
        user_id=uuid4(),
        username=NEW_USERNAME,
        email="other@example.com",
        password="hashed_pw",
        created_at=get_datetime(),
    )
    db_sess.scalar.side_effect = [mock_user_current, mock_user_existing]

    response = await ac.post("/auth/change-username", json={"username": NEW_USERNAME})
    assert response.status_code == 400
    assert response.json()["detail"] == "Username already exists."


@pytest.mark.asyncio
async def test_change_email_request_success(client):
    ac, db_sess, mock_redis_client, mock_email_service, _, _, _ = client

    mock_user = Users(
        user_id=uuid4(TEST_USER_ID),
        username=TEST_USERNAME,
        email=TEST_EMAIL,
        password="hashed_pw",
        created_at=get_datetime(),
    )
    db_sess.scalar.side_effect = [mock_user, None]  # First for current user, second for new email existence

    response = await ac.post("/auth/change-email", json={"email": NEW_EMAIL})
    assert response.status_code == 202
    assert response.json()["message"] == "A verification code has been sent to your email."

    mock_redis_client.scan_iter.assert_called_once()
    mock_redis_client.set.assert_called_once()
    redis_key, redis_value_str, ex = mock_redis_client.set.call_args[0]
    assert redis_key.startswith(f"{REDIS_CHANGE_EMAIL_KEY_PREFIX}{TEST_USER_ID}:")
    redis_payload = json.loads(redis_value_str)
    assert redis_payload["action"] == "change_email"
    assert redis_payload["new_value"] == NEW_EMAIL

    mock_email_service.send_email.assert_called_once()
    args, _ = mock_email_service.send_email.call_args
    assert args[0] == TEST_EMAIL
    assert "Confirm Your Email Change" in args[1]
    assert "Your verification code is:" in args[2]


@pytest.mark.asyncio
async def test_change_email_already_exists(client):
    ac, db_sess, _, _, _, _, _ = client

    mock_user_current = Users(
        user_id=uuid4(TEST_USER_ID),
        username=TEST_USERNAME,
        email=TEST_EMAIL,
        password="hashed_pw",
        created_at=get_datetime(),
    )
    mock_user_existing = Users(
        user_id=uuid4(),
        username="otheruser",
        email=NEW_EMAIL,
        password="hashed_pw",
        created_at=get_datetime(),
    )
    db_sess.scalar.side_effect = [mock_user_current, mock_user_existing]

    response = await ac.post("/auth/change-email", json={"email": NEW_EMAIL})
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already exists."


@pytest.mark.asyncio
async def test_change_password_request_success(client):
    ac, db_sess, mock_redis_client, mock_email_service, _, _, _ = client

    mock_user = Users(
        user_id=uuid4(TEST_USER_ID),
        username=TEST_USERNAME,
        email=TEST_EMAIL,
        password="hashed_pw",
        created_at=get_datetime(),
    )
    db_sess.scalar.return_value = mock_user

    response = await ac.post("/auth/change-password", json={"password": NEW_PASSWORD})
    assert response.status_code == 202
    assert response.json()["message"] == "A verification code has been sent to your email."

    mock_redis_client.scan_iter.assert_called_once()
    mock_redis_client.set.assert_called_once()
    redis_key, redis_value_str, ex = mock_redis_client.set.call_args[0]
    assert redis_key.startswith(f"{REDIS_CHANGE_PASSWORD_KEY_PREFIX}{TEST_USER_ID}")
    redis_payload = json.loads(redis_value_str)
    assert redis_payload["action"] == "change_password"
    assert redis_payload["new_value"] == NEW_PASSWORD

    mock_email_service.send_email.assert_called_once()
    args, _ = mock_email_service.send_email.call_args
    assert args[0] == TEST_EMAIL
    assert "Confirm Your Password Change" in args[1]
    assert "Your verification code is:" in args[2]


@pytest.mark.asyncio
async def test_verify_action_change_username_success(client):
    ac, db_sess, mock_redis_client, _, _, _, _ = client

    verification_code = "ABCDEF"
    redis_key = f"change_username:{TEST_USER_ID}:{verification_code}"
    mock_redis_client.get.return_value = json.dumps(
        {"user_id": TEST_USER_ID, "action": "change_username", "new_value": NEW_USERNAME}
    )
    db_sess.scalar.return_value = None # Ensure new username doesn't exist

    response = await ac.post("/auth/verify-action", json={"code": verification_code, "action": "change_username"})
    assert response.status_code == 200
    assert response.json()["message"] == "Username changed successfully."

    mock_redis_client.get.assert_called_once_with(redis_key)
    mock_redis_client.delete.assert_called_once_with(redis_key)
    db_sess.execute.assert_called_once() # For update
    db_sess.commit.assert_called_once()


@pytest.mark.asyncio
async def test_verify_action_change_username_already_taken(client):
    ac, db_sess, mock_redis_client, _, _, _, _ = client

    verification_code = "ABCDEF"
    redis_key = f"change_username:{TEST_USER_ID}:{verification_code}"
    mock_redis_client.get.return_value = json.dumps(
        {"user_id": TEST_USER_ID, "action": "change_username", "new_value": NEW_USERNAME}
    )
    db_sess.scalar.return_value = Users(user_id=uuid4(), username=NEW_USERNAME, email="other@example.com", password="", created_at=get_datetime()) # New username already exists

    response = await ac.post("/auth/verify-action", json={"code": verification_code, "action": "change_username"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Username already taken."

    mock_redis_client.get.assert_called_once_with(redis_key)
    mock_redis_client.delete.assert_called_once_with(redis_key)
    db_sess.execute.assert_not_called()
    db_sess.commit.assert_not_called()


@pytest.mark.asyncio
async def test_verify_action_change_email_success(client):
    ac, db_sess, mock_redis_client, _, _, _, mock_remove_jwt = client

    verification_code = "ABCDEF"
    redis_key = f"change_email:{TEST_USER_ID}:{verification_code}"
    mock_redis_client.get.return_value = json.dumps(
        {"user_id": TEST_USER_ID, "action": "change_email", "new_value": NEW_EMAIL}
    )

    response = await ac.post("/auth/verify-action", json={"code": verification_code, "action": "change_email"})
    assert response.status_code == 200
    assert "Set-Cookie" in response.headers # JWT removal cookie

    mock_redis_client.get.assert_called_once_with(redis_key)
    mock_redis_client.delete.assert_called_once_with(redis_key)
    assert db_sess.execute.call_count == 2 # Two update calls
    db_sess.commit.assert_called_once()
    mock_remove_jwt.assert_called_once() # remove_jwt is called inside verify_action


@pytest.mark.asyncio
async def test_verify_action_change_password_success(client):
    ac, db_sess, mock_redis_client, _, _, _, mock_remove_jwt = client

    verification_code = "ABCDEF"
    redis_key = f"change_password:{TEST_USER_ID}:{verification_code}"
    mock_redis_client.get.return_value = json.dumps(
        {"user_id": TEST_USER_ID, "action": "change_password", "new_value": NEW_PASSWORD}
    )

    response = await ac.post("/auth/verify-action", json={"code": verification_code, "action": "change_password"})
    assert response.status_code == 200
    assert "Set-Cookie" in response.headers # JWT removal cookie
    assert response.json()["message"] == "Password changed successfully."

    mock_redis_client.get.assert_called_once_with(redis_key)
    mock_redis_client.delete.assert_called_once_with(redis_key)
    assert db_sess.execute.call_count == 2 # Two update calls
    db_sess.commit.assert_called_once()
    mock_remove_jwt.assert_called_once() # remove_jwt is called inside verify_action


@pytest.mark.asyncio
async def test_verify_action_invalid_code(client):
    ac, db_sess, mock_redis_client, _, _, _, _ = client

    verification_code = "ABCDEF"
    redis_key = f"change_username:{TEST_USER_ID}:{verification_code}"
    mock_redis_client.get.return_value = None

    response = await ac.post("/auth/verify-action", json={"code": verification_code, "action": "change_username"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired verification code."

    mock_redis_client.get.assert_called_once_with(redis_key)
    mock_redis_client.delete.assert_not_called() # No deletion if code not found
    db_sess.commit.assert_not_called()


@pytest.mark.asyncio
async def test_verify_action_unauthorised_user_id(client):
    ac, db_sess, mock_redis_client, _, _, _, _ = client

    verification_code = "ABCDEF"
    redis_key = f"change_username:{TEST_USER_ID}:{verification_code}"
    mock_redis_client.get.return_value = json.dumps(
        {"user_id": str(uuid4()), "action": "change_username", "new_value": NEW_USERNAME} # Mismatched user_id
    )

    response = await ac.post("/auth/verify-action", json={"code": verification_code, "action": "change_username"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorised request."

    mock_redis_client.get.assert_called_once_with(redis_key)
    mock_redis_client.delete.assert_called_once_with(redis_key) # Code is deleted after attempt
    db_sess.commit.assert_not_called()