"""In-process bridge to a KnoxMap install.

KnoxMap is a Flask app. Rather than talking to a running window over HTTP
(the desktop launcher picks a random port every time), we import its Flask
`app` and call its routes through `app.test_client()`. The same route code
runs - with the same validation of tags, zone limits and map names - but no
server or window has to be open.

This module must run on KnoxMap's own interpreter (its `.venv`), because the
routes import KnoxMap's pinned dependencies.
"""
from __future__ import annotations

import os
import re
import sys
import threading
from pathlib import Path
from typing import Any

DEFAULT_KNOXMAP_DIR = r"C:\Users\Jordan\Desktop\knoxmap"

# KnoxMap's own rule for map folder names (web/generation.py SAFE_NAME keeps
# these characters); checked here so a bad name fails before any import work.
_SAFE_MAP_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")


class KnoxMapError(Exception):
    """A KnoxMap route refused the request, or KnoxMap could not be loaded."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class KnoxBridge:
    def __init__(self, knoxmap_dir: str | os.PathLike | None = None):
        self.dir = Path(knoxmap_dir or os.environ.get("KNOXMAP_DIR")
                        or DEFAULT_KNOXMAP_DIR).resolve()
        self._app = None
        self._lock = threading.Lock()

    # --- loading -----------------------------------------------------------

    def _load(self):
        if self._app is not None:
            return self._app
        with self._lock:
            if self._app is not None:
                return self._app
            if not (self.dir / "app.py").is_file():
                raise KnoxMapError(
                    f"No KnoxMap install at {self.dir} (app.py not found). "
                    f"Set KNOXMAP_DIR to the folder that holds app.py.")
            if str(self.dir) not in sys.path:
                sys.path.insert(0, str(self.dir))
            # KnoxMap resolves its paths from __file__, but some tools it runs
            # assume they start in its folder.
            os.chdir(self.dir)
            # app.py calls sys.stdout.reconfigure() on import. Under the MCP
            # stdio transport fd 1 has been diverted and that call raises
            # OSError 22, so stdout is pointed at stderr for the import only.
            real_stdout = sys.stdout
            sys.stdout = sys.stderr
            try:
                from app import app  # type: ignore[import-not-found]
            except Exception as exc:  # noqa: BLE001 - reported to the caller
                import traceback
                traceback.print_exc(file=sys.stderr)
                raise KnoxMapError(
                    f"KnoxMap at {self.dir} could not be loaded: {exc!r}. "
                    f"Is this server running on KnoxMap's .venv Python?") from exc
            finally:
                sys.stdout = real_stdout
            try:  # what app.py wanted: build chatter never raises on encoding
                sys.stdout.reconfigure(errors="replace")
            except (AttributeError, OSError, ValueError):
                pass
            self._app = app
            return app

    @property
    def output_dir(self) -> Path:
        return self.dir / "output"

    # --- calling routes ----------------------------------------------------

    def request(self, method: str, path: str, *, json: Any = None,
                query: dict | None = None) -> Any:
        """Call a KnoxMap route and return its JSON body.

        Raises KnoxMapError with KnoxMap's own error message on a 4xx/5xx.
        """
        app = self._load()
        with app.test_client() as client:
            resp = client.open(path, method=method, json=json,
                               query_string=query)
            data = resp.get_json(silent=True)
            text = None if data is not None else resp.get_data(as_text=True)
        if resp.status_code >= 400:
            msg = (data or {}).get("error") if isinstance(data, dict) else None
            raise KnoxMapError(msg or (text or "")[:500]
                               or f"HTTP {resp.status_code}", resp.status_code)
        return data if data is not None else text

    def get(self, path: str, **query) -> Any:
        return self.request("GET", path, query=query or None)

    def post(self, path: str, body: Any) -> Any:
        return self.request("POST", path, json=body)

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def check_map_name(name: str) -> str:
        if not isinstance(name, str) or not _SAFE_MAP_NAME.match(name):
            raise KnoxMapError(
                f"Bad map name {name!r}: use letters, digits, '_' or '-' "
                f"(see list_maps).", 400)
        return name
