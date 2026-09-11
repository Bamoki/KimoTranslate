"""Errores de dominio. Sin mensajes con secretos (ver core.logging)."""


class KimoError(Exception):
    pass


class NotFound(KimoError):
    pass


class BadTransition(KimoError):
    pass


class Conflict(KimoError):
    pass


class Unauthorized(KimoError):
    pass
