import json
import os

import pytest

from src.engine.enums import Side
from src.engine.events import LogEvent
from src.engine.events.enums import LogEventType, OrderEventType
# Importing WALogger through execution context to prevent
# incorrect referencing
from src.engine.execution_context import WALogger
from src.engine.restoration.engine_restorer_v2 import EngineRestorerV2
from tests.utils import create_new_order_command


@pytest.fixture
def clean_walogger_singleton():
    """Helper to clear WALogger instances to ensure fresh file handles."""
    WALogger._instances.clear()
    WALogger._log_file = None
    yield
    WALogger._instances.clear()
    WALogger._log_file = None


def test_wal_resumes_logging_mid_execution_after_crash(
    clean_walogger_singleton, user_id_a, symbol, tmp_dir, mocker
):
    """
    Scenario:
    1. The system receives a New Order Command.
    2. It logs the 'command' to disk.
    3. SYSTEM CRASHES immediately (The subsequent 'order_placed' event is never written).
    4. System restarts (Restoration).

    Expected Behavior:
    1. Restorer reads the 1 line (Command).
    2. Restorer executes the command.
    3. The execution triggers 'log_order_event'.
    4. The predicate in Restorer detects we have exhausted the log file.
    5. WALogger is allowed to write the missing 'order_placed' event to the file.
    """

    # 1. Setup paths
    snapshot_folder = os.path.join(tmp_dir, "snapshots", symbol)
    os.makedirs(snapshot_folder, exist_ok=True)
    wal_path = os.path.join(tmp_dir, "crash.log")

    # 2. Create the Command
    cmd = create_new_order_command(
        user_id=user_id_a,
        symbol=symbol,
        side=Side.ASK,
        quantity=10,
        price=100.0,
    )

    # 3. Simulate the "Crash State": Write ONLY the command to the WAL
    # We wrap it in the standard LogEvent structure
    log_entry = LogEvent(type=LogEventType.COMMAND, data=cmd)

    with open(wal_path, "w") as f:
        f.write(log_entry.model_dump_json() + "\n")

    # Verify initial state: File has exactly 1 line
    with open(wal_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 1

    # 4. Prepare Restoration
    # We must open the file in append mode and set it to WALogger
    # so the engine can write to it when it "wakes up"
    wal_file_handle = open(wal_path, "a")
    WALogger.set_file(wal_file_handle)

    restorer = EngineRestorerV2(wal_fpath=wal_path)
    restorer.get_restored_engine()

    # Close handle to ensure flush
    wal_file_handle.close()

    # 6. Verify Result
    with open(wal_path, "r") as f:
        final_lines = f.readlines()

    # The file should now contain 2 lines:
    # 1. The original Command
    # 2. The OrderPlaced event that was generated during restoration
    assert len(final_lines) == 2, final_lines

    line_1 = json.loads(final_lines[0])
    line_2 = json.loads(final_lines[1])

    assert line_1["type"] == LogEventType.COMMAND
    assert line_1["data"]["id"] == cmd["id"]

    assert line_2["type"] == LogEventType.ORDER_EVENT
    assert line_2["data"]["type"] == OrderEventType.ORDER_PLACED
    assert line_2["data"]["order_id"] == cmd["order_id"]
