"""Single plug point into the core app.

In app/main.py:
    from simulator import register
    register(app)

Controlled by the SIMULATOR_ENABLED env flag (default: enabled in this
dev stack). If the simulator package is removed, the guarded import in
main.py fails silently and the system runs unchanged.
"""

import logging

from fastapi import FastAPI

from app.config import get_settings

logger = logging.getLogger("simulator")


def register(app: FastAPI) -> None:
    if not get_settings().SIMULATOR_ENABLED:
        logger.info("simulator disabled via SIMULATOR_ENABLED")
        return
    from simulator.api import router

    app.include_router(router)
    logger.info("simulator mounted at /admin/simulator")
