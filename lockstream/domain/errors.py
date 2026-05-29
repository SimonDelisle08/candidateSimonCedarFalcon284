"""Errors the domain raises. The API layer is the only thing that maps these to HTTP codes."""


class DomainError(Exception):
    """Base for everything the domain throws."""


class PayloadValidationError(DomainError):
    """The event is malformed on its own - bad or missing payload field. Maps to 422."""


class DomainRuleViolation(DomainError):
    """A well-formed event that conflicts with the current state. Maps to 409."""
