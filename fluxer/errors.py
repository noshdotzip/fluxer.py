class FluxerError(Exception):
    """Base exception for fluxer.py compatibility layer."""


class DiscordException(FluxerError):
    """Parity alias for discord.py exceptions."""


class ClientException(DiscordException):
    pass


class HTTPException(DiscordException):
    def __init__(self, status, message, data=None):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.data = data


class Forbidden(HTTPException):
    pass


class NotFound(HTTPException):
    pass


class HTTPError(HTTPException):
    pass


class LoginFailure(ClientException):
    pass


class GatewayError(DiscordException):
    pass
