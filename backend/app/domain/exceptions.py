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


class ValidationError(DomainError):
    """Invalid input data for a domain operation."""


class CellOverlapError(DomainError):
    """A specialist already has a cell in this time range."""


class CellInUseError(DomainError):
    """The cell has active bookings and cannot be removed or moved."""


class DoesNotFitError(DomainError):
    """The selected services do not fit into the free part of the cell."""


class ConflictError(DomainError):
    """Resource already exists or operation conflicts with current state."""
