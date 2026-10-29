class DomainError(Exception):
    pass


class SlotTakenError(DomainError):
    pass


class NotFoundError(DomainError):
    pass


class ForbiddenError(DomainError):
    pass


class BotAlreadyLinkedError(DomainError):
    """Raised when a Telegram bot_id is already attached to another tenant."""
