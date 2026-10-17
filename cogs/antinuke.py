"""
cogs/antinuke.py
----------------
Protects the server from coordinated raid attacks by monitoring:
  - Mass bans
  - Mass channel deletions
  - Mass role deletions
  - Mass member kicks
  - Webhook creation spikes

If any single moderator exceeds the configured threshold within a rolling
60-second window, the bot will:
  1. Strip their top role (remove mod perms)
  2. Apply the lockdown / quarantine role
  3. Post an alert to the log channel
"""
import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Optional

from utils.db import servers_col


# --- thresholds (events per 60 seconds before triggering lockdown) ---
THRESHOLDS = {
    "ban":             3,
    "kick":            3,
    "channel_delete":  3,
    "role_delete":     3,
    "webhook_create":  3,
}


class AntiNuke(commands.Cog):
    """Anti-raid / anti-nuke protection system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # { guild_id: { user_id: { action: [timestamp, ...] } } }
        self._log: dict[int, dict[int, dict[str, list[datetime]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _track(self, guild_id: int, user_id: int, action: str) -> int:
        """Record an event and return how many occurred in the last 60 seconds."""
        window = self._now() - timedelta(seconds=60)
        bucket = self._log[guild_id][user_id][action]
        # Prune old events
        self._log[guild_id][user_id][action] = [t for t in bucket if t > window]
        self._log[guild_id][user_id][action].append(self._now())
        return len(self._log[guild_id][user_id][action])

    async def _get_config(self, guild_id: int) -> dict:
        doc = await servers_col.find_one({"guild_id": guild_id},
                                         {"log_channel": 1, "lockdown_role": 1})
        return doc or {}

    async def _lockdown(self, guild: discord.Guild, offender: discord.Member, action: str, count: int):
        """Apply quarantine to the offending member and alert the log channel."""
        config = await self._get_config(guild.id)

        # 1. Apply lockdown role
        lockdown_role_id = config.get("lockdown_role")
        if lockdown_role_id:
            lockdown_role = guild.get_role(lockdown_role_id)
            if lockdown_role:
                try:
                    await offender.add_roles(lockdown_role, reason="AntiNuke: automatic quarantine")
                except discord.Forbidden:
                    pass

        # 2. Remove their highest role (strip mod power)
        try:
            if offender.top_role and offender.top_role != guild.default_role:
                await offender.remove_roles(offender.top_role,
                                            reason="AntiNuke: stripping elevated permissions")
        except discord.Forbidden:
            pass

        # 3. Log the incident
        log_channel_id = config.get("log_channel")
        if log_channel_id:
            channel = guild.get_channel(log_channel_id)
            if channel:
                embed = discord.Embed(
                    title="🚨 AntiNuke Triggered",
                    description=(
                        f"**Offender:** {offender.mention} (`{offender.id}`)\n"
                        f"**Action:** `{action}` — {count} times in 60 seconds\n"
                        f"**Punishment:** Lockdown role applied, top role removed."
                    ),
                    color=discord.Color.dark_red(),
                    timestamp=self._now(),
                )
                embed.set_footer(text="Review the offender and take manual action if needed.")
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    # ── audit log fetching ────────────────────────────────────────────────

    async def _get_audit_user(self, guild: discord.Guild,
                              action: discord.AuditLogAction,
                              target_id: Optional[int] = None) -> Optional[discord.Member]:
        """Fetch the most recent audit log entry user for a given action."""
        try:
            async for entry in guild.audit_logs(limit=1, action=action):
                if target_id is None or (entry.target and entry.target.id == target_id):
                    return guild.get_member(entry.user.id)
        except discord.Forbidden:
            pass
        return None

    # ── event listeners ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        offender = await self._get_audit_user(guild, discord.AuditLogAction.ban, user.id)
        if not offender or offender.bot:
            return
        count = self._track(guild.id, offender.id, "ban")
        if count >= THRESHOLDS["ban"]:
            await self._lockdown(guild, offender, "ban", count)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Catch manual kicks via audit log."""
        guild = member.guild
        offender = await self._get_audit_user(guild, discord.AuditLogAction.kick, member.id)
        if not offender or offender.bot:
            return
        count = self._track(guild.id, offender.id, "kick")
        if count >= THRESHOLDS["kick"]:
            await self._lockdown(guild, offender, "kick", count)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        offender = await self._get_audit_user(guild, discord.AuditLogAction.channel_delete, channel.id)
        if not offender or offender.bot:
            return
        count = self._track(guild.id, offender.id, "channel_delete")
        if count >= THRESHOLDS["channel_delete"]:
            await self._lockdown(guild, offender, "channel_delete", count)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        offender = await self._get_audit_user(guild, discord.AuditLogAction.role_delete, role.id)
        if not offender or offender.bot:
            return
        count = self._track(guild.id, offender.id, "role_delete")
        if count >= THRESHOLDS["role_delete"]:
            await self._lockdown(guild, offender, "role_delete", count)

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.TextChannel):
        guild = channel.guild
        offender = await self._get_audit_user(guild, discord.AuditLogAction.webhook_create)
        if not offender or offender.bot:
            return
        count = self._track(guild.id, offender.id, "webhook_create")
        if count >= THRESHOLDS["webhook_create"]:
            await self._lockdown(guild, offender, "webhook_create", count)

    # ── manual antinuke commands ──────────────────────────────────────────

    @commands.command(name="antinukestatus")
    @commands.has_guild_permissions(administrator=True)
    async def antinuke_status(self, ctx: commands.Context):
        """Show current AntiNuke thresholds and configuration."""
        config = await self._get_config(ctx.guild.id)
        log_ch = ctx.guild.get_channel(config.get("log_channel", 0))
        lockdown_role = ctx.guild.get_role(config.get("lockdown_role", 0))

        embed = discord.Embed(title="🛡️ AntiNuke Status", color=discord.Color.blurple(),
                              timestamp=self._now())
        embed.add_field(name="Log Channel",
                        value=log_ch.mention if log_ch else "❌ Not set (`!setlogchannel`)",
                        inline=False)
        embed.add_field(name="Lockdown Role",
                        value=lockdown_role.mention if lockdown_role else "❌ Not set (`!setlockdownrole`)",
                        inline=False)
        thresholds_text = "\n".join(f"`{k}` — max **{v}** per 60s" for k, v in THRESHOLDS.items())
        embed.add_field(name="Thresholds", value=thresholds_text, inline=False)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiNuke(bot))
