"""
Warm Runner Out-of-Process Worker Daemon (warm_runner_worker.py).

Backward-compatibility facade delegating to core.test_engine.worker.
Executes unittest targets in an isolated sub-process with stdout/stderr capture.
"""

import sys
from .test_engine.worker import execute_single_request, worker_main_loop

__all__ = [
    "execute_single_request",
    "worker_main_loop",
]

if __name__ == "__main__":
    sys.exit(worker_main_loop())
