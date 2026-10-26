"""Inject synchronous AI functions. One active worker, no pending work queue."""
import asyncio
from concurrent.futures import Future
import copy
from threading import Lock, Thread
from time import monotonic
from typing import Protocol


class AIAdapter(Protocol):
    def interpret_destination(self, payload: dict) -> dict: ...
    def choose_guidance(self, payload: dict) -> dict: ...


class AIBoundary:
    def __init__(self, adapter=None, budget=1.0):
        self.adapter = adapter
        self.budget = min(budget, 1.0)
        self._busy = Lock()

    async def call(self, method, payload):
        if self.adapter is None or not self._busy.acquire(blocking=False):
            return None
        future = Future()
        started = monotonic()
        safe_payload = copy.deepcopy(payload)

        def work():
            try:
                future.set_result(getattr(self.adapter, method)(safe_payload))
            except Exception:
                future.set_result(None)
            finally:
                self._busy.release()

        # A timeout rejects the result; it does not stop Python code. A hung adapter
        # retains the single slot, so repeated requests cannot accumulate workers.
        Thread(target=work, daemon=True, name='bus-ai-adapter').start()
        try:
            result = await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), self.budget)
            return result if monotonic() - started <= self.budget else None
        except asyncio.TimeoutError:
            return None
