"""In-memory session store for the game. Sessions die with the process —
they are toys, not data. Old sessions are pruned lazily."""

import time
import uuid

from simulator.engine import SimulationEngine

SESSION_TTL_SECONDS = 6 * 60 * 60
MAX_SESSIONS = 64

_sessions: dict[str, dict] = {}


def prune() -> None:
    now = time.time()
    expired = [sid for sid, s in _sessions.items() if now - s["created_at"] > SESSION_TTL_SECONDS]
    for sid in expired:
        del _sessions[sid]
    while len(_sessions) >= MAX_SESSIONS:
        oldest = min(_sessions.items(), key=lambda kv: kv[1]["created_at"])[0]
        del _sessions[oldest]


def create(engine: SimulationEngine) -> str:
    prune()
    sid = uuid.uuid4().hex[:12]
    _sessions[sid] = {"engine": engine, "created_at": time.time()}
    return sid


def get(sid: str) -> SimulationEngine | None:
    session = _sessions.get(sid)
    if session is None:
        return None
    session["created_at"] = time.time()
    return session["engine"]


def delete(sid: str) -> bool:
    return _sessions.pop(sid, None) is not None
