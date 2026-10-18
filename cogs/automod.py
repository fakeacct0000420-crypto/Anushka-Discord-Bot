"""
cogs/automod.py
---------------
Warning system with automatic strike-based escalation.

Strike ladder:
  1st  – DM warning
  2nd  – 15-minute timeout (cool-down)
  3rd  – 12-hour timeout  (final warning)
  4th  – Kick
  5th+ – Permanent ban
"""
import os
import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
from typing import Optional

from pymongo import ReturnDocument

from utils.db import warns_col, servers_col
from utils.checks import is_moderator

# Encryption is optional — gracefully skip if ENCRYPTION_KEY is not set
_ENCRYPT = bool(os.getenv("ENCRYPTION_KEY"))
if _ENCRYPT:
    from utils.crypto import encrypt as _enc, decrypt as _dec
else:
    def _enc(v): return v   # noqa: E731
    def _dec(v): return v   # noqa: E731


class AutoMod(commands.Cog):
    """Warning and auto-escalation cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _embed(color: discord.Color, title: str, description: str) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=color,
                             timestamp=datetime.now(timezone.utc))

    async def _add_strike(self, guild_id: int, user_id: int, reason: str) -> int:
        """Increment and return the user's current strike count.
        Reason strings are AES-256-GCM encrypted before storage so MongoDB
        never holds plaintext moderation data.
        """
        encrypted_reason = _enc(reason)   # no-op if ENCRYPTION_KEY not set
        doc = await warns_col.find_one_and_update(
            {"guild_id": guild_id, "user_id": user_id},
            {
                "$inc": {"strikes": 1},
                "$push": {
                    "history": {
                        "reason": encrypted_reason,
                        "issued_at": self._utcnow(),
                        "encrypted": _ENCRYPT,
                    }
                },
                "$setOnInsert": {"created_at": self._utcnow()},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return doc["strikes"]

    async def _post_log(self, guild: discord.Guild, embed: discord.Embed):
        """Send an embed to the guild's log channel (if configured)."""
        doc = await servers_col.find_one({"guild_id": guild.id}, {"log_channel": 1})
        if not doc:
            return
        channel_id = doc.get("log_channel")
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    async def _escalate(self, ctx: commands.Context, member: discord.Member, strike: int):
        """Execute the punishment tier matching the current strike count."""
        guild = ctx.guild

        if strike == 1:
            # First strike – DM only, already sent by the warn command
            return

        elif strike == 2:
            until = self._utcnow() + timedelta(minutes=15)
            try:
                await member.edit(timed_out_until=until, reason="2nd strike – 15-minute timeout")
            except discord.Forbidden:
                await ctx.send("⚠️ Couldn't apply timeout (missing permissions).")
                return
            embed = self._embed(discord.Color.gold(), "⏱️ 2nd Strike — 15-Minute Timeout",
                                f"{member.mention} has been timed out for 15 minutes.")
            await ctx.send(embed=embed)
            await self._post_log(guild, embed)

        elif strike == 3:
            until = self._utcnow() + timedelta(hours=12)
            try:
                await member.edit(timed_out_until=until, reason="3rd strike – 12-hour timeout")
            except discord.Forbidden:
                await ctx.send("⚠️ Couldn't apply timeout (missing permissions).")
                return
            embed = self._embed(discord.Color.orange(), "⏱️ 3rd Strike — 12-Hour Timeout",
                                f"{member.mention} has been timed out for 12 hours.")
            await ctx.send(embed=embed)
            await self._post_log(guild, embed)

        elif strike == 4:
            try:
                await member.kick(reason="4th strike – automatic kick")
            except discord.Forbidden:
                await ctx.send("⚠️ Couldn't kick (missing permissions).")
                return
            embed = self._embed(discord.Color.red(), "⚔️ 4th Strike — Kicked",
                                f"{member.mention} was kicked from the server.")
            await ctx.send(embed=embed)
            await self._post_log(guild, embed)

        else:  # 5+
            try:
                await member.ban(reason=f"Strike {strike} – permanent ban", delete_message_days=0)
            except discord.Forbidden:
                await ctx.send("⚠️ Couldn't ban (missing permissions).")
                return
            embed = self._embed(discord.Color.dark_red(), "⛔ Permanent Ban",
                                f"{member.mention} was permanently banned (strike {strike}).")
            await ctx.send(embed=embed)
            await self._post_log(guild, embed)

    # ── commands ──────────────────────────────────────────────────────────

    @commands.command(name="warn")
    @is_moderator()
    async def warn(self, ctx: commands.Context, member: discord.Member,
                   *, reason: Optional[str] = "No reason provided."):
        """Warn a member and automatically escalate based on total strikes.
        Usage: !warn @User [reason]
        """
        if member.bot:
            return await ctx.send("You can't warn a bot.")

        strikes = await self._add_strike(ctx.guild.id, member.id, reason)

        # Always DM the user their warning
        try:
            await member.send(embed=self._embed(
                discord.Color.yellow(),
                f"⚠️ Warning — {ctx.guild.name}",
                f"**Reason:** {reason}\n**Strike:** {strikes}\n**Moderator:** {ctx.author}"
            ))
        except discord.Forbidden:
            await ctx.send("⚠️ Could not DM the user (DMs closed).")

        await ctx.send(embed=self._embed(
            discord.Color.yellow(),
            f"⚠️ Warning Issued — Strike {strikes}",
            f"{member.mention} has been warned.\n**Reason:** {reason}"
        ))

        # Auto-escalate for strike 2+
        await self._escalate(ctx, member, strikes)

    @commands.command(name="strikes")
    @is_moderator()
    async def strikes(self, ctx: commands.Context, member: discord.Member):
        """View a member's current strike count and history.
        Usage: !strikes @User
        """
        doc = await warns_col.find_one({"guild_id": ctx.guild.id, "user_id": member.id})
        if not doc or doc.get("strikes", 0) == 0:
            return await ctx.send(embed=self._embed(discord.Color.green(), "✅ Clean Record",
                                                    f"{member.mention} has no strikes."))

        history = doc.get("history", [])
        def _safe_reason(h: dict) -> str:
            raw = h.get("reason", "—")
            if h.get("encrypted"):
                try:
                    return _dec(raw)
                except Exception:
                    return "[decryption error]"
            return raw
        lines = [f"`{i+1}.` {_safe_reason(h)} — <t:{int(h['issued_at'].timestamp())}:R>"
                 for i, h in enumerate(history[-10:])]  # last 10

        embed = self._embed(discord.Color.orange(), f"⚠️ Strikes for {member}",
                             f"**Total strikes:** {doc['strikes']}\n\n" + "\n".join(lines))
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="clearstrikes")
    @commands.has_guild_permissions(administrator=True)
    async def clear_strikes(self, ctx: commands.Context, member: discord.Member):
        """Clear ALL strikes for a member (admin only).
        Usage: !clearstrikes @User
        """
        await warns_col.delete_one({"guild_id": ctx.guild.id, "user_id": member.id})
        await ctx.send(embed=self._embed(discord.Color.green(), "✅ Strikes Cleared",
                                         f"All strikes removed for {member.mention}."))

    # ── error handling ────────────────────────────────────────────────────

    @warn.error
    @strikes.error
    async def warn_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(embed=self._embed(discord.Color.red(), "❌ Unauthorized",
                                             "You don't have the moderator role."))
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(embed=self._embed(discord.Color.red(), "❌ Not Found",
                                             "Member not found."))
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
