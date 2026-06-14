from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ErrorCategory:
    INVOCATION = "invocation"
    CONFIG_VALIDATION = "config_validation"
    EXECUTION_FAILURE = "execution_failure"
    INTERRUPTED = "interrupted"
    INTERNAL = "internal_error"


EXIT_CODES = {
    ErrorCategory.INVOCATION: 2,
    ErrorCategory.CONFIG_VALIDATION: 6,
    ErrorCategory.EXECUTION_FAILURE: 10,
    ErrorCategory.INTERRUPTED: 130,
    ErrorCategory.INTERNAL: 1,
}


class CliError(Exception):
    category = ErrorCategory.INTERNAL

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        run_refs: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})
        self.run_refs = dict(run_refs or {})


class InvocationError(CliError):
    category = ErrorCategory.INVOCATION


class ConfigCliError(CliError):
    category = ErrorCategory.CONFIG_VALIDATION


class ExecutionFailureError(CliError):
    category = ErrorCategory.EXECUTION_FAILURE


class InterruptedCliError(CliError):
    category = ErrorCategory.INTERRUPTED


class InternalCliError(CliError):
    category = ErrorCategory.INTERNAL


class ParserExit(Exception):
    def __init__(self, status: int = 0, message: str | None = None) -> None:
        super().__init__(message or "")
        self.status = status
        self.message = message


def exit_code_for(error: CliError) -> int:
    return EXIT_CODES.get(error.category, EXIT_CODES[ErrorCategory.INTERNAL])
