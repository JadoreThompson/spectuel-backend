import uuid
from datetime import datetime, timedelta

import pytest
from unittest.mock import MagicMock

from src.engine.events.enums import BalanceEventType
from src.engine.restoration.balance_manager_restorer import BalanceManagerRestorer
from src.engine.config import REDIS_CASH_BALANCE_PREFIX, REDIS_CASH_BALANCE_HKEY_PREFIX


# Mock Data helper
class MockEventLog:
    def __init__(self, type, data, timestamp):
        self.data = data
        self.data["type"] = type
        self.timestamp = timestamp
        self.event_id = data.get("id", str(uuid.uuid4()))


@pytest.fixture
def mock_redis_clients(mocker):
    # We mock the clients imported in the restorer module
    main_redis = mocker.patch("src.engine.restoration.balance_manager_restorer.REDIS_CLIENT_SYNC")
    backup_redis = mocker.patch(
        "src.engine.restoration.balance_manager_restorer.BACKUP_REDIS_CLIENT_SYNC"
    )

    # Mock lastsave to return a valid datetime
    main_redis.lastsave.return_value = datetime.now() - timedelta(hours=1)

    # Mock keys scanning
    main_redis.keys.return_value = []

    # Mock pipeline for backup
    backup_redis.pipeline.return_value.__enter__.return_value = MagicMock()

    return main_redis, backup_redis


@pytest.fixture
def mock_db_session(mocker):
    # Mock the get_db_sess context manager
    mock_sess = MagicMock()
    mocker.patch(
        "src.engine.restoration.balance_manager_restorer.get_db_sess_sync",
        return_value=MagicMock(__enter__=lambda _: mock_sess),
    )
    return mock_sess


def test_restoration_snapshot_copy(mock_redis_clients, mock_db_session):
    """
    Verify that existing keys in Main Redis are copied to Backup Redis.
    """
    main, backup = mock_redis_clients

    # Setup Main Redis State
    main.keys.return_value = [b"user:123:balance"]
    main.type.return_value = b"string"
    main.get.return_value = b"100.0"

    # Setup DB to return empty logs
    mock_res = MagicMock()
    mock_res.yield_per.return_value = []  # No logs
    mock_db_session.execute.return_value = mock_res

    restorer = BalanceManagerRestorer()
    success = restorer.restore_balance_manager()

    assert success is True
    # Verify Flush
    backup.flushdb.assert_called_once()
    # Verify Value Copy
    backup.set.assert_called_with(b"user:123:balance", b"100.0")


def test_restoration_log_replay(mock_redis_clients, mock_db_session, user_id_a, mocker):
    """
    Verify that logs occurring after the snapshot are applied to the Backup Redis.
    """
    main, backup = mock_redis_clients

    # 1. Setup DB Logs: A Cash Increase Event
    event_id = str(uuid.uuid4())
    log_data = {"id": event_id, "user_id": user_id_a, "amount": 50.0, "version": "1"}
    log_entry = MockEventLog(
        BalanceEventType.CASH_BALANCE_INCREASED, log_data, 1234567890
    )

    mock_res = MagicMock()
    mock_res.yield_per.return_value = [[log_entry]]  # Generator yielding list of rows
    mock_db_session.execute.return_value = mock_res

    # 2. Setup BalanceManager inside restorer to use our mock backup redis
    # The Restorer initializes BalanceManager(redis_client=BACKUP_REDIS_CLIENT)
    # We want to spy on the Lua script registration/execution

    # Since BalanceManager is instantiated inside __init__, we need to rely on the
    # mocked backup_redis passed into it.
    mock_script = MagicMock()
    mock_script.return_value = 150.0  # Return new balance
    backup.register_script.return_value = mock_script

    # 3. Execute
    restorer = BalanceManagerRestorer()
    restorer.restore_balance_manager()

    # 4. Assert
    # Verify the script was called with the correct keys for User A
    val_key = f"{REDIS_CASH_BALANCE_PREFIX}{user_id_a}"
    log_key = f"{REDIS_CASH_BALANCE_HKEY_PREFIX}{user_id_a}"

    # Check that the Increase Cash Balance Lua script was called
    # We have multiple scripts, finding the right one (increase calls _script_update)
    assert mock_script.called
    call_args = mock_script.call_args
    assert call_args is not None

    # Verify Keys [ValueKey, LogKey] and Args [EventID, Amount]
    assert call_args.kwargs["keys"] == [val_key, log_key]
    assert call_args.kwargs["args"] == [event_id, 50.0]


def test_settlement_replay_logic(
    mock_redis_clients, mock_db_session, user_id_a, symbol
):
    """
    Verify complex event (Ask Settled) is dispatched correctly.
    """
    main, backup = mock_redis_clients

    # Create Ask Settled Event Log
    # Note: The restorer expects a dict in log.data that matches Pydantic model
    log_data = {
        "id": str(uuid.uuid4()),
        "user_id": user_id_a,
        "symbol": symbol,
        "quantity": 10.0,
        "price": 100.0,
        "version": 1,
        # Pydantic model usually requires sub-events, but if they handle defaults or
        # use default_factory, we might get away with minimal data.
        # Assuming the dict stored in DB is the full dump:
        "asset_balance_decreased": {
            "id": str(uuid.uuid4()),
            "version": 1,
            "user_id": user_id_a,
            "symbol": symbol,
            "amount": 10.0,
            "type": "asset_balance_decreased",
        },
        "asset_escrow_decreased": {
            "id": str(uuid.uuid4()),
            "version": 1,
            "user_id": user_id_a,
            "symbol": symbol,
            "amount": 10.0,
            "type": "asset_escrow_decreased",
        },
        "cash_balance_increased": {
            "id": str(uuid.uuid4()),
            "version": 1,
            "user_id": user_id_a,
            "amount": 1000.0,
            "type": "cash_balance_increased",
        },
    }

    log_entry = MockEventLog(BalanceEventType.ASK_SETTLED, log_data, 1234567890)

    mock_res = MagicMock()
    mock_res.yield_per.return_value = [[log_entry]]
    mock_db_session.execute.return_value = mock_res

    # Mock Scripts
    mock_script = MagicMock()
    backup.register_script.return_value = mock_script

    restorer = BalanceManagerRestorer()
    restorer.restore_balance_manager()

    # The Settle Ask script should be called.
    # It takes 6 keys and 5 args.
    assert mock_script.called
    call_args = mock_script.call_args
    # Verify quantity (Arg 0) and Price (Arg 1) are passed
    assert call_args.kwargs["args"][0] == 10.0
    assert call_args.kwargs["args"][1] == 100.0
