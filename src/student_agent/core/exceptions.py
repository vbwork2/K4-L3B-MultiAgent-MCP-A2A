class WorkflowError(RuntimeError):
    """Base error for the student workflow."""


class ToolBudgetExceeded(WorkflowError):
    """Raised before an MCP call would exceed the case budget."""


class AgentNotImplementedError(WorkflowError):
    """Raised by an agent whose domain logic is not implemented yet."""


class VerificationError(WorkflowError):
    """Raised when an output cannot pass final verification."""
