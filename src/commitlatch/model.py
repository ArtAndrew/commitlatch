"""Public contracts. An unknown outcome is never permission to retry."""

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


class CommitLatchError(Exception):
    pass


class ActionConflict(CommitLatchError):
    """The same business key was reused with different input or adapter."""


class ActionBusy(CommitLatchError):
    pass


class UnknownOutcome(CommitLatchError):
    pass


class ActionFailed(CommitLatchError):
    pass


class InvalidState(CommitLatchError):
    pass


class OwnershipLost(CommitLatchError):
    pass


class DefinitelyNotApplied(Exception):
    """Adapter assertion: this attempt has no effect and cannot apply later.

    Do NOT translate generic timeouts, HTTP errors, or missing search results
    into this exception. Only raise it when the provider contract proves it.
    """


def canonical(value: Any) -> str:
    """Strict JSON only; no coercion of keys, tuples, non-finite floats, etc."""
    def check(item: Any) -> None:
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for element in item:
                check(element)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for element in item.values():
                check(element)
            return
        raise ValueError("Values must be finite, strict JSON with string keys")

    check(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Reconciliation:
    status: str
    result: Any = None
    evidence: Optional[str] = None

    @classmethod
    def succeeded(cls, result: Any, evidence: str) -> "Reconciliation":
        return cls("SUCCEEDED", result, evidence)

    @classmethod
    def unknown(cls, reason: str) -> "Reconciliation":
        return cls("UNKNOWN", evidence=reason)

    @classmethod
    def not_applied(cls, evidence: str) -> "Reconciliation":
        """Proof of non-execution AND no remaining in-flight attempt."""
        return cls("FAILED", evidence=evidence)


class Adapter(Protocol):
    # Include provider account/scope and contract version in this stable name.
    name: str

    def execute(self, effect_key: str, arguments: Dict[str, Any]) -> Any:
        ...

    def reconcile(self, effect_key: str,
                  arguments: Dict[str, Any]) -> Reconciliation:
        ...
