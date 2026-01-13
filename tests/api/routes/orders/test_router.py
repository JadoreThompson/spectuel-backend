import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime

from api.app import app
from api.dependencies import depends_db_sess
from api.types import JWTPayload
from engine.enums import OrderStatus, Side, OrderType, StrategyType
from db_models import Orders
from config import COOKIE_ALIAS
from utils import get_datetime

# Mock data
USER_ID = str(uuid4())
ORDER_ID = str(uuid4())
GROUP_ID = str(uuid4())


@pytest.fixture
def mock_jwt_payload():
    return JWTPayload(
        sub=USER_ID, exp=1234567890, em="test@example.com", authenticated=True
    )


@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    # Mock execute result for list queries
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    session.get.return_value = None
    return session


import pytest_asyncio


@pytest_asyncio.fixture
async def client(mock_jwt_payload, mock_db_session):
    # Override DB dependency
    async def override_db_sess():
        yield mock_db_session

    app.dependency_overrides[depends_db_sess] = override_db_sess

    # Mock JWT validation
    with patch(
        "services.jwt_service.JWTService.validate_jwt", new_callable=AsyncMock
    ) as mock_validate:
        mock_validate.return_value = mock_jwt_payload

        # Mock put_command to avoid Kafka interaction
        with patch(
            "api.routes.orders.router.put_command", new_callable=AsyncMock
        ) as mock_put:
            with patch(
                "api.routes.orders.service.service.put_command", new_callable=AsyncMock
            ) as mock_service_put:
                # Mock OrderService start/stop to avoid aiokafka creation
                with patch(
                    "api.routes.orders.service.OrderService.start",
                    new_callable=AsyncMock,
                ), patch(
                    "api.routes.orders.service.OrderService.stop",
                    new_callable=AsyncMock,
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        ac.cookies = {COOKIE_ALIAS: "valid_token"}
                        yield ac, mock_db_session, mock_put, mock_service_put

    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_create_single_order(client):
    ac, db_sess, _, mock_service_put = client

    payload = {
        "strategy_type": "single",
        "symbol": "BTCUSD",
        "order_type": "limit",
        "side": "bid",
        "quantity": 1.0,
        "limit_price": 50000.0,
    }

    response = await ac.post("/orders/", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert "order_id" in data
    assert data["status"] == "accepted"

    # Verify DB interaction
    assert db_sess.add.called
    assert db_sess.commit.called

    # Verify Command interaction
    assert mock_service_put.called
    call_args = mock_service_put.call_args
    command = call_args[0][0]
    assert command.symbol == "BTCUSD"
    assert command.strategy_type == StrategyType.SINGLE
    assert command.limit_price == 50000.0


@pytest.mark.asyncio
async def test_create_oco_order(client):
    ac, db_sess, _, mock_service_put = client

    payload = {
        "strategy_type": "oco",
        "symbol": "BTCUSD",
        "legs": [
            {
                "order_type": "limit",
                "side": "bid",
                "quantity": 1.0,
                "limit_price": 40000.0,
            },
            {
                "order_type": "stop",
                "side": "bid",
                "quantity": 1.0,
                "stop_price": 60000.0,
            },
        ],
    }

    response = await ac.post("/orders/oco", json=payload)
    print(f"DEBUG: response.json() = {response.json()}")
    assert response.status_code == 202, response.text
    data = response.json()
    assert "group_id" in data
    assert len(data["legs"]) == 2

    assert db_sess.add.call_count == 2
    assert mock_service_put.called


@pytest.mark.asyncio
async def test_create_oto_order(client):
    ac, db_sess, _, mock_service_put = client

    payload = {
        "strategy_type": "oto",
        "symbol": "BTCUSD",
        "parent": {
            "order_type": "limit",
            "side": "bid",
            "quantity": 1.0,
            "limit_price": 50000.0,
        },
        "child": {
            "order_type": "limit",
            "side": "ask",
            "quantity": 1.0,
            "limit_price": 55000.0,
        },
    }

    response = await ac.post("/orders/oto", json=payload)
    assert response.status_code == 202, response.text
    data = response.json()
    assert "group_id" in data
    assert "parent_id" in data
    assert "child_id" in data

    assert db_sess.add.call_count == 2
    assert mock_service_put.called


@pytest.mark.asyncio
async def test_create_otoco_order(client):
    ac, db_sess, _, mock_service_put = client

    payload = {
        "strategy_type": "otoco",
        "symbol": "BTCUSD",
        "parent": {
            "order_type": "limit",
            "side": "bid",
            "quantity": 1.0,
            "limit_price": 50000.0,
        },
        "oco_legs": [
            {
                "order_type": "limit",
                "side": "ask",
                "quantity": 1.0,
                "limit_price": 55000.0,
            },
            {
                "order_type": "stop",
                "side": "ask",
                "quantity": 1.0,
                "stop_price": 45000.0,
            },
        ],
    }

    response = await ac.post("/orders/otoco", json=payload)
    assert response.status_code == 202, response.text
    data = response.json()
    assert "group_id" in data
    assert "parent_id" in data
    assert len(data["legs"]) == 2

    assert db_sess.add.call_count == 3
    assert mock_service_put.called


@pytest.mark.asyncio
async def test_get_orders(client):
    ac, db_sess, _, _ = client

    # Mock DB response
    mock_order = Orders(
        order_id=uuid4(),
        user_id=uuid4(),
        symbol="BTCUSD",
        side=Side.BID,
        order_type=OrderType.LIMIT,
        quantity=1.0,
        limit_price=50000.0,
        status=OrderStatus.PENDING,
        created_at=get_datetime(),
        strategy_type=StrategyType.SINGLE,
    )
    db_sess.execute.return_value.scalars.return_value.all.return_value = [mock_order]

    response = await ac.get("/orders/")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["symbol"] == "BTCUSD"


@pytest.mark.asyncio
async def test_get_order_by_id(client):
    ac, db_sess, _, _ = client

    order_id = uuid4()
    mock_order = Orders(
        order_id=order_id,
        user_id=uuid4(),  # This needs to match the mocked JWT user_id
        symbol="BTCUSD",
        side=Side.BID,
        order_type=OrderType.LIMIT,
        quantity=1.0,
        limit_price=50000.0,
        status=OrderStatus.PENDING,
        created_at=get_datetime(),
        strategy_type=StrategyType.SINGLE,
    )
    # Fix user_id to match mock_jwt_payload
    mock_order.user_id = uuid4()  # Wait, I need to match USER_ID

    # But I can't easily access USER_ID inside the test unless I import it or pass it.
    # I defined USER_ID at module level.
    mock_order.user_id = USER_ID

    db_sess.get.return_value = mock_order

    response = await ac.get(f"/orders/{order_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["order_id"] == str(order_id)


@pytest.mark.asyncio
async def test_get_order_not_found(client):
    ac, db_sess, _, _ = client
    db_sess.get.return_value = None

    response = await ac.get(f"/orders/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_orders_by_group(client):
    ac, db_sess, _, _ = client

    group_id = uuid4()
    mock_order = Orders(
        order_id=uuid4(),
        user_id=USER_ID,
        order_group_id=group_id,
        symbol="BTCUSD",
        side=Side.BID,
        order_type=OrderType.LIMIT,
        quantity=1.0,
        limit_price=50000.0,
        status=OrderStatus.PENDING,
        # created_at=datetime.utcnow(),
        created_at=get_datetime(),
        strategy_type=StrategyType.SINGLE,
    )
    db_sess.execute.return_value.scalars.return_value.all.return_value = [mock_order]

    response = await ac.get(f"/orders/groups/{group_id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "BTCUSD"


@pytest.mark.asyncio
async def test_modify_order(client):
    ac, db_sess, mock_router_put, _ = client

    order_id = uuid4()
    mock_order = Orders(
        order_id=order_id,
        user_id=USER_ID,
        symbol="BTCUSD",
        side=Side.BID,
        order_type=OrderType.LIMIT,
        quantity=1.0,
        limit_price=50000.0,
        status=OrderStatus.PENDING,
        # created_at=datetime.utcnow(),
        created_at=get_datetime(),
        strategy_type=StrategyType.SINGLE,
    )
    db_sess.scalar.return_value = mock_order

    payload = {"limit_price": 51000.0}
    response = await ac.patch(f"/orders/{order_id}", json=payload)
    assert response.status_code == 202

    assert mock_router_put.called
    call_args = mock_router_put.call_args
    command = call_args[0][0]
    assert command.limit_price == 51000.0


@pytest.mark.asyncio
async def test_modify_filled_order(client):
    ac, db_sess, _, _ = client

    order_id = uuid4()
    mock_order = Orders(
        order_id=order_id,
        user_id=USER_ID,
        symbol="BTCUSD",
        side=Side.BID,
        order_type=OrderType.LIMIT,
        quantity=1.0,
        limit_price=50000.0,
        status=OrderStatus.FILLED,  # Filled
        # created_at=datetime.utcnow(),
        created_at=get_datetime(),
        strategy_type=StrategyType.SINGLE,
    )
    db_sess.scalar.return_value = mock_order

    payload = {"limit_price": 51000.0}
    response = await ac.patch(f"/orders/{order_id}", json=payload)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_cancel_order(client):
    ac, db_sess, mock_router_put, _ = client

    order_id = uuid4()
    mock_order = Orders(
        order_id=order_id,
        user_id=USER_ID,
        symbol="BTCUSD",
        side=Side.BID,
        order_type=OrderType.LIMIT,
        quantity=1.0,
        limit_price=50000.0,
        status=OrderStatus.PENDING,
        created_at=get_datetime(),
        strategy_type=StrategyType.SINGLE,
    )
    db_sess.execute.return_value.scalar_one_or_none.return_value = mock_order

    response = await ac.delete(f"/orders/{order_id}")
    assert response.status_code == 202

    assert mock_router_put.called
    call_args = mock_router_put.call_args
    command = call_args[0][0]
    assert command.order_id == order_id
