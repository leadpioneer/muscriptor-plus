"""Bounded store for stem artifacts produced by a preprocessing run.

The server keeps nothing on disk between requests as a rule, but downloaded
stems have to survive their transcription's SSE response: the browser only
starts fetching them after the final event. This store hands out run-scoped
stem files and reaps old run directories (TTL + a small cap) so disk usage
stays bounded even if the user never downloads anything.
"""

import shutil
import threading
import time
from pathlib import Path


class StemStore:
    """In-memory registry of `run_id → {stem name → file path}`."""

    def __init__(
        self,
        ttl_s: float = 3600.0,
        max_runs: int = 8,
        time_fn=time.time,
    ) -> None:
        self._ttl_s = ttl_s
        self._max_runs = max_runs
        self._time_fn = time_fn
        self._lock = threading.Lock()
        # run_id → (directory, {stem: path}, creation time)
        self._entries: dict[str, tuple[Path, dict[str, Path], float]] = {}

    def register(self, run_id: str, directory: Path, stems: dict[str, Path]) -> None:
        """Record a finished run's stems, reaping expired runs first."""
        with self._lock:
            self._sweep_locked()
            self._entries[run_id] = (Path(directory), dict(stems), self._time_fn())
            # Hard cap: drop the oldest runs beyond the limit, newest kept.
            while len(self._entries) > self._max_runs:
                oldest = min(self._entries, key=lambda r: self._entries[r][2])
                entry_dir, _, _ = self._entries.pop(oldest)
                shutil.rmtree(entry_dir, ignore_errors=True)

    def get(self, run_id: str, stem: str) -> Path | None:
        """Path of `stem` for `run_id`, or None when unknown/expired."""
        with self._lock:
            self._sweep_locked()
            entry = self._entries.get(run_id)
            if entry is None:
                return None
            return entry[1].get(stem)

    def _sweep_locked(self) -> None:
        now = self._time_fn()
        expired = [
            run_id
            # Entries are (directory, {stem: path}, creation time); only the
            # creation time decides expiry here.
            for run_id, (_, _, created) in self._entries.items()
            if now - created > self._ttl_s
        ]
        for run_id in expired:
            directory, _, _ = self._entries.pop(run_id)
            shutil.rmtree(directory, ignore_errors=True)

    def sweep_orphans(self, parent: Path) -> None:
        """Delete leftover run directories, even unregistered ones.

        A client disconnecting mid-run (or a crash between preprocessing and
        registration) leaves a `muscriptor-stems-*` directory behind; this
        removes any such directory older than the TTL. Called before a new run
        creates its own directory, so disk usage stays bounded.
        """
        now = self._time_fn()
        for directory in Path(parent).glob("muscriptor-stems-*"):
            try:
                if now - directory.stat().st_mtime > self._ttl_s:
                    shutil.rmtree(directory, ignore_errors=True)
            except OSError:
                continue
