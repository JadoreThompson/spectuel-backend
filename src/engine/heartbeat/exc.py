class ValidationError(Exception):
    """Raised when a message was sent with invalid fields"""

    pass


class HeartbeatTimeoutError(Exception):
    """
    Raised when the client fail to send a heartbeat within a
    specific time
    """

    pass
