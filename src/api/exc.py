class JWTError(Exception):
    """Custom exception for jwt validation errors."""

    pass


class ApiKeyError(Exception):
    """Custom exception for api key errors."""

    pass


class CustomValidationError(Exception):
    def __init__(self, status_code: int, msg: str):
        self.status_code = status_code
        self.msg = msg
