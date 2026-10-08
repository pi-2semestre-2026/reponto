"""Reponto Simulator — a stock-management game that stress-tests the real
recommender (LightGBM + blend) against an independent stochastic reality.

Fully segregated from the core app: nothing in `app/` depends on this
package, and the package only *reads* the real model artifact and seed
baselines. It can be deleted without touching the rest of the system.
"""

from simulator.mount import register

__all__ = ["register"]
