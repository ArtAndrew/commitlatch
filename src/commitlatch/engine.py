"""Execution is opt-in; reconciliation never silently invokes execute()."""

import math
import time
from typing import Any, Dict

from .ledger import SQLiteLedger
from .model import (ActionBusy, ActionConflict, ActionFailed, Adapter,
                    DefinitelyNotApplied, InvalidState, Reconciliation,
                    UnknownOutcome, canonical)


class CommitLatch:
    def __init__(self, ledger: SQLiteLedger, lease_seconds: float = 30, clock=time.time):
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("lease_seconds must be finite and positive")
        self.ledger = ledger
        self.lease_seconds = lease_seconds
        self.clock = clock

    def run(self, namespace: str, key: str, adapter: Adapter,
            arguments: Dict[str, Any]) -> Any:
        action = self.ledger.prepare(namespace, key, adapter.name, arguments, self.clock())
        decision, action, token = self.ledger.claim(
            action["id"], "execute", self.clock(), self.lease_seconds)
        if decision == "SUCCEEDED":
            return action["result"]
        if decision == "BUSY":
            raise ActionBusy("Operation has an active execution or reconciliation claim")
        if decision == "FAILED":
            raise ActionFailed("Operation was not applied; explicitly retry_failed() to retry")
        if decision != "CLAIMED":
            raise UnknownOutcome("Outcome is unknown; reconcile before any further decision")
        try:
            # Use the durable snapshot, not the caller's mutable arguments.
            result = adapter.execute(action["id"], action["arguments"])
            canonical(result)
        except DefinitelyNotApplied:
            self.ledger.finish(action["id"], token, "FAILED", self.clock(),
                               evidence="Adapter certified no effect and no future execution")
            raise ActionFailed("Adapter certified this attempt was not applied") from None
        except Exception as error:
            # Error messages may contain credentials. Persist only the class name.
            self.ledger.finish(action["id"], token, "UNKNOWN", self.clock(),
                               evidence="Adapter execution raised " + type(error).__name__)
            raise UnknownOutcome("External outcome could not be recorded; reconcile it") from None
        self.ledger.finish(action["id"], token, "SUCCEEDED", self.clock(), result=result,
                           evidence="Adapter returned a serializable success result")
        return result

    def reconcile(self, namespace: str, key: str, adapter: Adapter) -> Dict[str, Any]:
        action = self.ledger.get(namespace, key)
        if action["adapter"] != adapter.name:
            raise ActionConflict("Reconciliation adapter does not match the original operation")
        decision, action, token = self.ledger.claim(
            action["id"], "reconcile", self.clock(), self.lease_seconds)
        if decision in ("SUCCEEDED", "FAILED"):
            return action
        if decision == "BUSY":
            raise ActionBusy("Operation still has an active claim; wait for its expiry")
        if decision != "CLAIMED":
            raise InvalidState("Only uncertain or expired operations can be reconciled")
        try:
            outcome = adapter.reconcile(action["id"], action["arguments"])
            if not isinstance(outcome, Reconciliation):
                raise ValueError("Adapter must return Reconciliation")
            if outcome.status not in ("SUCCEEDED", "UNKNOWN", "FAILED"):
                raise ValueError("Invalid reconciliation status")
            if not isinstance(outcome.evidence, str) or not outcome.evidence.strip():
                raise ValueError("Reconciliation requires evidence or an uncertainty reason")
            canonical(outcome.result)
        except Exception as error:
            outcome = Reconciliation.unknown("Reconciliation raised " + type(error).__name__)
        return self.ledger.finish(action["id"], token, outcome.status, self.clock(),
                                  result=outcome.result, evidence=outcome.evidence)

    def retry_failed(self, namespace: str, key: str) -> None:
        action = self.ledger.get(namespace, key)
        self.ledger.retry_failed(action["id"], self.clock())
