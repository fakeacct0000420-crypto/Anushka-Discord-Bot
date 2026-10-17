"""
core.py
-------
Bot entry point.  Loads environment variables, initialises intents,
registers all cogs automatically, and starts the bot.

Usage:
  python core.py
"""
import os
import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

# ── environment ────────────────────────────────────────────────────────────────
load_dotenv()

TOKEN  = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "!")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set.  Copy .env.example → .env and fill it in.")

# ── logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("core")

# ── intents ────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members          = True   # Required for member fetching in moderation / antinuke
intents.message_content  = True   # Required to read command messages
intents.voice_states     = True   # Required for music commands


# ── bot subclass ───────────────────────────────────────────────────────────────
class Codex(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or(PREFIX),
            intents=intents,
            case_insensitive=True,
            help_command=None,          # Replaced by custom help below
            strip_after_prefix=True,
        )

    async def setup_hook(self):
        """Load every .py file found in the cogs/ directory."""
        cogs_path = Path(__file__).parent / "cogs"
        for file in sorted(cogs_path.glob("*.py")):
            if file.stem.startswith("_"):
                continue  # skip __init__ etc.
            ext = f"cogs.{file.stem}"
            try:
                await self.load_extension(ext)
                log.info("Loaded cog: %s", ext)
            except Exception as exc:
                log.error("Failed to load cog %s: %s", ext, exc)

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{PREFIX}help | {len(self.guilds)} servers"
            )
        )
        log.info("Ready.  Serving %d guild(s).", len(self.guilds))

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Global fallback error handler."""
        if isinstance(error, commands.CommandNotFound):
            return  # Silently ignore unknown commands
        if isinstance(error, commands.NoPrivateMessage):
            return await ctx.send("This command can only be used in a server.")
        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(f"⏳ Slow down! Try again in `{error.retry_after:.1f}s`.")
        if isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(error.missing_permissions)
            return await ctx.send(f"❌ I'm missing permissions: `{perms}`")
        # Unhandled – log it
        log.exception("Unhandled command error in %s: %s", ctx.command, error)


# ── custom help command ────────────────────────────────────────────────────────
@commands.command(name="help")
async def help_cmd(ctx: commands.Context, *, query: str = None):
    """Show available commands or detail on a specific command/cog."""
    bot: Codex = ctx.bot
    prefix = PREFIX

    if query:
        cmd = bot.get_command(query)
        if cmd:
            embed = discord.Embed(
                title=f"📖 {prefix}{cmd.qualified_name}",
                description=cmd.help or "No description.",
                color=discord.Color.blurple(),
            )
            if cmd.aliases:
                embed.add_field(name="Aliases", value=", ".join(f"`{a}`" for a in cmd.aliases))
            return await ctx.send(embed=embed)
        return await ctx.send(f"No command named `{query}` found.")

    # General help
    embed = discord.Embed(
        title="📖 Codex — Command Reference",
        description=f"Prefix: `{prefix}` — Use `{prefix}help <command>` for details on any command.",
        color=discord.Color.blurple(),
    )

    cog_order = ["Moderation", "AutoMod", "Music", "AntiNuke"]
    shown = set()

    for cog_name in cog_order:
        cog = bot.cogs.get(cog_name)
        if not cog:
            continue
        cmds = [c for c in cog.get_commands() if not c.hidden]
        if cmds:
            embed.add_field(
                name=f"{'🛡️' if 'Mod' in cog_name else '🎵' if 'Music' in cog_name else '🚨'} {cog_name}",
                value=" ".join(f"`{prefix}{c.name}`" for c in cmds),
                inline=False,
            )
            shown.add(cog_name)

    # Any other loaded cogs not in cog_order
    for cog_name, cog in bot.cogs.items():
        if cog_name in shown:
            continue
        cmds = [c for c in cog.get_commands() if not c.hidden]
        if cmds:
            embed.add_field(
                name=f"⚙️ {cog_name}",
                value=" ".join(f"`{prefix}{c.name}`" for c in cmds),
                inline=False,
            )

    embed.set_footer(text=f"Serving {len(bot.guilds)} server(s) | {len(bot.commands)} commands total")
    await ctx.send(embed=embed)


# ── entrypoint ────────────────────────────────────────────────────────────────
async def main():
    bot = Codex()
    bot.add_command(help_cmd)
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
