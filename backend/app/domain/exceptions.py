class DomainError(Exception):
    pass


class SlotTakenError(DomainError):
    pass


class NotFoundError(DomainError):
    pass


class ForbiddenError(DomainError):
    pass
