# utils/__init__.py
# Makes utils a package; exposes shared db and checks at the top level.
from .db import db, servers_col, warns_col
from .checks import is_moderator, is_music_dj

__all__ = ["db", "servers_col", "warns_col", "is_moderator", "is_music_dj"]
