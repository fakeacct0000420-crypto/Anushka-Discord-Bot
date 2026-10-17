"""
cogs/moderation.py
------------------
Kick, timeout, untimeout, and warn-bypass commands gated behind the
moderator role stored in MongoDB.  Admin-only setup commands let server
owners register their moderator / music / lockdown roles without ever
touching a config file.
"""
import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
from typing import Optional

from utils.db import servers_col
from utils.checks import is_moderator


class Moderation(commands.Cog):
    """Server moderation commands backed by dynamic MongoDB role config."""

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

    # ── moderation commands ───────────────────────────────────────────────

    @commands.command(name="kick")
    @is_moderator()
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = "No reason provided."):
        """Kick a member from the server.
        Usage: !kick @User [reason]
        """
        if member.top_role >= ctx.author.top_role and not ctx.author.guild_permissions.administrator:
            return await ctx.send(embed=self._embed(discord.Color.red(), "❌ Error",
                                                    "You cannot kick someone with an equal or higher role."))
        try:
            await member.send(embed=self._embed(discord.Color.orange(), f"Kicked from {ctx.guild.name}",
                                                f"**Reason:** {reason}\n**Moderator:** {ctx.author}"))
        except discord.Forbidden:
            pass  # DMs closed
        await member.kick(reason=f"[{ctx.author}] {reason}")
        await ctx.send(embed=self._embed(discord.Color.green(), "✅ Member Kicked",
                                         f"{member.mention} has been kicked.\n**Reason:** {reason}"))

    @commands.command(name="ban")
    @is_moderator()
    @commands.has_guild_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = "No reason provided."):
        """Permanently ban a member.
        Usage: !ban @User [reason]
        """
        if member.top_role >= ctx.author.top_role and not ctx.author.guild_permissions.administrator:
            return await ctx.send(embed=self._embed(discord.Color.red(), "❌ Error",
                                                    "You cannot ban someone with an equal or higher role."))
        try:
            await member.send(embed=self._embed(discord.Color.red(), f"Banned from {ctx.guild.name}",
                                                f"**Reason:** {reason}\n**Moderator:** {ctx.author}"))
        except discord.Forbidden:
            pass
        await member.ban(reason=f"[{ctx.author}] {reason}", delete_message_days=0)
        await ctx.send(embed=self._embed(discord.Color.green(), "⛔ Member Banned",
                                         f"{member.mention} has been permanently banned.\n**Reason:** {reason}"))

    @commands.command(name="unban")
    @is_moderator()
    @commands.has_guild_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: int, *, reason: Optional[str] = "No reason provided."):
        """Unban a user by their ID.
        Usage: !unban <user_id> [reason]
        """
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=f"[{ctx.author}] {reason}")
            await ctx.send(embed=self._embed(discord.Color.green(), "✅ User Unbanned",
                                             f"{user} (`{user_id}`) has been unbanned."))
        except discord.NotFound:
            await ctx.send(embed=self._embed(discord.Color.red(), "❌ Not Found",
                                             "That user ID was not found in the ban list."))

    @commands.command(name="timeout")
    @is_moderator()
    async def timeout_cmd(self, ctx: commands.Context, member: discord.Member, duration: int,
                          unit: str = "m", *, reason: Optional[str] = "No reason provided."):
        """Timeout a member.  Duration + unit (s/m/h/d).
        Usage: !timeout @User 30 m [reason]
        """
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        if unit not in multipliers:
            return await ctx.send("Unit must be one of: `s` (seconds), `m` (minutes), `h` (hours), `d` (days).")
        seconds = duration * multipliers[unit]
        if seconds > 60 * 60 * 24 * 28:
            return await ctx.send("Discord caps timeouts at **28 days**.")
        until = self._utcnow() + timedelta(seconds=seconds)
        try:
            await member.edit(timed_out_until=until, reason=f"[{ctx.author}] {reason}")
            await ctx.send(embed=self._embed(discord.Color.gold(), "⏱️ Member Timed Out",
                                             f"{member.mention} timed out for **{duration}{unit}**.\n**Reason:** {reason}"))
        except discord.Forbidden:
            await ctx.send(embed=self._embed(discord.Color.red(), "❌ Error",
                                             "Missing permissions to timeout this user."))

    @commands.command(name="untimeout")
    @is_moderator()
    async def untimeout(self, ctx: commands.Context, member: discord.Member):
        """Remove a timeout from a member.
        Usage: !untimeout @User
        """
        try:
            await member.edit(timed_out_until=None)
            await ctx.send(embed=self._embed(discord.Color.green(), "✅ Timeout Removed",
                                             f"{member.mention} can speak again."))
        except discord.Forbidden:
            await ctx.send(embed=self._embed(discord.Color.red(), "❌ Error",
                                             "Missing permissions to remove this timeout."))

    @commands.command(name="purge")
    @is_moderator()
    @commands.has_guild_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int):
        """Delete the last N messages in the current channel.
        Usage: !purge 20
        """
        if not 1 <= amount <= 500:
            return await ctx.send("Amount must be between 1 and 500.")
        deleted = await ctx.channel.purge(limit=amount + 1)  # +1 to include the command message
        msg = await ctx.send(embed=self._embed(discord.Color.green(), "🗑️ Purged",
                                               f"Deleted **{len(deleted) - 1}** messages."))
        await msg.delete(delay=4)

    # ── role setup commands (admin only) ─────────────────────────────────

    @commands.command(name="setmodrole")
    @commands.has_guild_permissions(administrator=True)
    async def set_mod_role(self, ctx: commands.Context, role: discord.Role):
        """Set the moderator role for this server.
        Usage: !setmodrole @Mods
        """
        await servers_col.update_one({"guild_id": ctx.guild.id},
                                     {"$set": {"moderator_role": role.id}}, upsert=True)
        await ctx.send(embed=self._embed(discord.Color.green(), "✅ Role Saved",
                                         f"Moderator role set to {role.mention}."))

    @commands.command(name="setmusicrole")
    @commands.has_guild_permissions(administrator=True)
    async def set_music_role(self, ctx: commands.Context, role: discord.Role):
        """Set the music / DJ role for this server.
        Usage: !setmusicrole @DJ
        """
        await servers_col.update_one({"guild_id": ctx.guild.id},
                                     {"$set": {"music_role": role.id}}, upsert=True)
        await ctx.send(embed=self._embed(discord.Color.green(), "✅ Role Saved",
                                         f"Music / DJ role set to {role.mention}."))

    @commands.command(name="setlockdownrole")
    @commands.has_guild_permissions(administrator=True)
    async def set_lockdown_role(self, ctx: commands.Context, role: discord.Role):
        """Set the quarantine / lockdown role for this server.
        Usage: !setlockdownrole @Quarantine
        """
        await servers_col.update_one({"guild_id": ctx.guild.id},
                                     {"$set": {"lockdown_role": role.id}}, upsert=True)
        await ctx.send(embed=self._embed(discord.Color.green(), "✅ Role Saved",
                                         f"Lockdown role set to {role.mention}."))

    @commands.command(name="setlogchannel")
    @commands.has_guild_permissions(administrator=True)
    async def set_log_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the moderation log channel.
        Usage: !setlogchannel #mod-logs
        """
        await servers_col.update_one({"guild_id": ctx.guild.id},
                                     {"$set": {"log_channel": channel.id}}, upsert=True)
        await ctx.send(embed=self._embed(discord.Color.green(), "✅ Log Channel Set",
                                         f"Moderation logs will be sent to {channel.mention}."))

    # ── error handling ────────────────────────────────────────────────────

    @kick.error
    @ban.error
    @timeout_cmd.error
    @untimeout.error
    @purge.error
    async def mod_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(embed=self._embed(discord.Color.red(), "❌ Unauthorized",
                                             "You don't have the moderator role."))
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(embed=self._embed(discord.Color.red(), "❌ Not Found",
                                             "Member not found. Mention them or use their ID."))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=self._embed(discord.Color.red(), "❌ Missing Argument",
                                             f"Missing required argument: `{error.param.name}`."))
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
