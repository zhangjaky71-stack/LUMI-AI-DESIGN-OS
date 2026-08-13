class AuthError(RuntimeError):
    code = "AUTH_ERROR"


class InvalidCredentials(AuthError):
    code = "INVALID_CREDENTIALS"


class RegistrationRejected(AuthError):
    code = "REGISTRATION_NOT_AVAILABLE"


class SessionInvalid(AuthError):
    code = "SESSION_INVALID"


class TokenInvalid(AuthError):
    code = "TOKEN_INVALID_OR_EXPIRED"


class PermissionDenied(AuthError):
    code = "PERMISSION_DENIED"
