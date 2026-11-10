"""The two helpers ``calibre.srv.render_book`` lends to the kepubifier.

The real module renders books for Calibre's content server; only a profiler
context manager and the worker-count heuristic (``calibre.library.page_count``)
are needed here.
"""
from __future__ import annotations

import os
from collections.abc import Sequence


class Profiler:
    def __init__(self) -> None:
        import cProfile
        self.profile = cProfile.Profile()

    def __enter__(self) -> None:
        self.profile.enable()

    def __exit__(self, *a: object) -> None:
        self.profile.disable()
        self.profile.create_stats()
        import pstats
        stats = pstats.Stats(self.profile)
        stats.sort_stats('cumulative').print_stats(30)


def calculate_number_of_workers(names: Sequence[str], in_process_container, max_workers: int) -> int:
    num_workers = min(os.cpu_count() or 1, len(names))
    if max_workers:
        num_workers = min(num_workers, max_workers)
    if num_workers > 1:
        if len(names) < 3 or sum(os.path.getsize(in_process_container.name_path_map[n]) for n in names) < 128 * 1024:
            num_workers = 1
    return num_workers
