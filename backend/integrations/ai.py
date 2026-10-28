"""Inject synchronous AI functions. One active worker, no pending work queue."""
import asyncio
from concurrent.futures import Future
import copy
import inspect
import json
from math import isfinite
from threading import Lock, Thread
from time import monotonic
from typing import Protocol


class AIAdapter(Protocol):
    def interpret_destination(self, payload: dict) -> dict: ...
    def choose_guidance(self, payload: dict) -> dict: ...


class AIBoundary:
    def __init__(self, adapter=None, budget=1.0):
        if not isfinite(budget) or budget <= 0:
            raise ValueError('AI adoption budget must be positive and finite')
        self.adapter = adapter
        self.budget = min(budget, 1.0)
        self._busy = Lock()

    async def call(self, method, payload):
        adapter = self.adapter
        if adapter is None or not self._busy.acquire(blocking=False):
            return None
        future = Future()
        started = monotonic()

        def work():
            try:
                if not future.set_running_or_notify_cancel():
                    return
                if monotonic() - started >= self.budget:
                    future.set_result(None)
                    return
                result = getattr(adapter, method)(safe_payload)
                if inspect.iscoroutine(result):
                    result.close()
                    result = None
                elif type(result) is not dict:
                    result = None
                # Accept an isolated JSON value; NaN, sets, model objects and
                # other non-JSON results are adapter failures, not API facts.
                future.set_result(json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False)))
            except Exception:
                if not future.done():
                    future.set_result(None)
            finally:
                self._busy.release()

        # A timeout rejects the result; it does not stop Python code. A hung adapter
        # retains the single slot, so repeated requests cannot accumulate workers.
        try:
            safe_payload = copy.deepcopy(payload)
            if monotonic() - started >= self.budget:
                self._busy.release()
                return None
            Thread(target=work, daemon=True, name='bus-ai-adapter').start()
        except Exception:
            self._busy.release()
            return None
        remaining = self.budget - (monotonic() - started)
        if remaining <= 0:
            return None
        try:
            result = await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), remaining)
            return result if monotonic() - started <= self.budget else None
        except asyncio.TimeoutError:
            return None
