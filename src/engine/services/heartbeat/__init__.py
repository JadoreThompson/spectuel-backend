"""
Heartbeat service module.

Provides a TCP server and client implementation to monitor
heartbeat messages for registered symbols. Also exposes
exceptions related to heartbeat validation and timeouts.
"""

from .client import HeartbeatClient
from .server import HeartbeatServer
from .exc import ValidationError, HeartbeatTimeoutError


__all__ = [
    "HeartbeatClient",
    "HeartbeatServer",
    "ValidationError",
    "HeartbeatTimeoutError",
]
