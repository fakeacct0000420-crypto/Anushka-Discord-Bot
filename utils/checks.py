"""
utils/checks.py
---------------
Custom command checks that read authorized roles from MongoDB
rather than relying on hardcoded IDs.
"""
from discord.ext import commands
from .db import servers_col


async def _get_role_id(guild_id: int, key: str) -> int | None:
    """Helper – fetch a single role ID from the server document."""
    doc = await servers_col.find_one({"guild_id": guild_id}, {key: 1})
    return doc.get(key) if doc else None


def is_moderator():
    """Check that the invoking member has the configured moderator role.
    Falls back gracefully when no role has been set yet.
    """
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False
        role_id = await _get_role_id(ctx.guild.id, "moderator_role")
        if role_id is None:
            # Nothing configured – only server admins may proceed
            return ctx.author.guild_permissions.administrator
        return any(r.id == role_id for r in ctx.author.roles)

    return commands.check(predicate)


def is_music_dj():
    """Check that the invoking member has the configured music / DJ role."""
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False
        role_id = await _get_role_id(ctx.guild.id, "music_role")
        if role_id is None:
            return ctx.author.guild_permissions.administrator
        return any(r.id == role_id for r in ctx.author.roles)

    return commands.check(predicate)
