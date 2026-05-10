"""Global checkpointer registry.

The AsyncPostgresSaver is initialized once at startup (main.py → graph/builder.py)
and stored here so node functions can access it without circular imports.
"""

from typing import Optional

_checkpointer: Optional[object] = None


def get_checkpointer():
    return _checkpointer


def set_checkpointer(cp) -> None:
    global _checkpointer
    _checkpointer = cp
