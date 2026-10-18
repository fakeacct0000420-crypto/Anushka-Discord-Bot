"""
cogs/music.py
-------------
Music / DJ commands gated behind the music role stored in MongoDB.
Uses yt-dlp for audio extraction and discord.py's voice client for playback.

Requirements:
  pip install yt-dlp PyNaCl
  FFmpeg must be installed and on your system PATH.
"""
import asyncio
import discord
from discord.ext import commands
from typing import Optional
import yt_dlp

from utils.checks import is_music_dj

# yt-dlp options – extract audio only, no playlist (yet)
YDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}

FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class MusicQueue:
    """Minimal per-guild music queue."""

    def __init__(self):
        self.queue: list[dict] = []
        self.current: Optional[dict] = None
        self.voice_client: Optional[discord.VoiceClient] = None
        self.loop: bool = False


class Music(commands.Cog):
    """Music commands for DJs and music-enabled members."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._queues: dict[int, MusicQueue] = {}

    def _get_queue(self, guild_id: int) -> MusicQueue:
        if guild_id not in self._queues:
            self._queues[guild_id] = MusicQueue()
        return self._queues[guild_id]

    @staticmethod
    def _embed(color: discord.Color, title: str, description: str = "") -> discord.Embed:
        return discord.Embed(title=title, description=description, color=color)

    async def _extract(self, query: str) -> Optional[dict]:
        """Run yt-dlp extraction in a thread pool to avoid blocking."""
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            try:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
            except yt_dlp.utils.DownloadError:
                return None
        if "entries" in info:
            info = info["entries"][0]
        return info

    def _play_next(self, guild_id: int):
        """Called when the current track ends; play the next or stop."""
        mq = self._get_queue(guild_id)
        if mq.loop and mq.current:
            # Re-queue the current track for looping
            mq.queue.insert(0, mq.current)
        if not mq.queue:
            mq.current = None
            return
        track = mq.queue.pop(0)
        mq.current = track
        try:
            source = discord.FFmpegPCMAudio(track["url"], **FFMPEG_OPTS)
            mq.voice_client.play(source, after=lambda _: self._play_next(guild_id))
        except Exception:
            self._play_next(guild_id)

    # ── commands ──────────────────────────────────────────────────────────

    @commands.command(name="play", aliases=["p"])
    @is_music_dj()
    async def play(self, ctx: commands.Context, *, query: str):
        """Play a song or add it to the queue.
        Usage: !play <URL or search terms>
        """
        if not ctx.author.voice:
            return await ctx.send(embed=self._embed(discord.Color.red(), "❌ Not in VC",
                                                    "Join a voice channel first."))

        mq = self._get_queue(ctx.guild.id)

        # Join or move to author's VC
        vc = ctx.voice_client
        if vc is None:
            vc = await ctx.author.voice.channel.connect()
            mq.voice_client = vc
        elif vc.channel != ctx.author.voice.channel:
            await vc.move_to(ctx.author.voice.channel)
            mq.voice_client = vc

        async with ctx.typing():
            info = await self._extract(query)

        if not info:
            return await ctx.send(embed=self._embed(discord.Color.red(), "❌ Not Found",
                                                    "Couldn't find anything for that query."))

        track = {"title": info.get("title", "Unknown"), "url": info["url"],
                 "webpage_url": info.get("webpage_url", ""), "requester": ctx.author}

        if vc.is_playing() or vc.is_paused():
            mq.queue.append(track)
            await ctx.send(embed=self._embed(discord.Color.blurple(), "📋 Added to Queue",
                                             f"[{track['title']}]({track['webpage_url']})\n"
                                             f"Position: **{len(mq.queue)}**"))
        else:
            mq.current = track
            try:
                source = discord.FFmpegPCMAudio(track["url"], **FFMPEG_OPTS)
                vc.play(source, after=lambda _: self._play_next(ctx.guild.id))
            except Exception as e:
                return await ctx.send(embed=self._embed(
                    discord.Color.red(), "❌ Audio Error",
                    f"Could not initialize audio playback: `{e}`\n(Ensure FFmpeg is installed and accessible on PATH)"
                ))
            await ctx.send(embed=self._embed(discord.Color.green(), "🎵 Now Playing",
                                             f"[{track['title']}]({track['webpage_url']})\n"
                                             f"Requested by {ctx.author.mention}"))

    @commands.command(name="skip", aliases=["s"])
    @is_music_dj()
    async def skip(self, ctx: commands.Context):
        """Skip the current track.
        Usage: !skip
        """
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await ctx.send(embed=self._embed(discord.Color.orange(), "⏭️ Skipped", "Moving to the next track."))
        else:
            await ctx.send(embed=self._embed(discord.Color.red(), "❌ Nothing Playing", ""))

    @commands.command(name="pause")
    @is_music_dj()
    async def pause(self, ctx: commands.Context):
        """Pause playback.  Use !resume to continue.
        Usage: !pause
        """
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await ctx.send(embed=self._embed(discord.Color.gold(), "⏸️ Paused", ""))
        else:
            await ctx.send(embed=self._embed(discord.Color.red(), "❌ Nothing Playing", ""))

    @commands.command(name="resume")
    @is_music_dj()
    async def resume(self, ctx: commands.Context):
        """Resume paused playback.
        Usage: !resume
        """
        vc = ctx.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await ctx.send(embed=self._embed(discord.Color.green(), "▶️ Resumed", ""))
        else:
            await ctx.send(embed=self._embed(discord.Color.red(), "❌ Not Paused", ""))

    @commands.command(name="stop")
    @is_music_dj()
    async def stop(self, ctx: commands.Context):
        """Stop playback and clear the queue.
        Usage: !stop
        """
        mq = self._get_queue(ctx.guild.id)
        mq.queue.clear()
        mq.current = None
        vc = ctx.voice_client
        if vc:
            vc.stop()
            await vc.disconnect()
        await ctx.send(embed=self._embed(discord.Color.red(), "⏹️ Stopped", "Queue cleared and disconnected."))

    @commands.command(name="queue", aliases=["q"])
    async def queue_list(self, ctx: commands.Context):
        """Show the current music queue.
        Usage: !queue
        """
        mq = self._get_queue(ctx.guild.id)
        if not mq.current and not mq.queue:
            return await ctx.send(embed=self._embed(discord.Color.blurple(), "📋 Queue", "Nothing in the queue."))

        lines = []
        if mq.current:
            lines.append(f"🎵 **Now Playing:** [{mq.current['title']}]({mq.current['webpage_url']})")
        for i, t in enumerate(mq.queue[:10], 1):
            lines.append(f"`{i}.` [{t['title']}]({t['webpage_url']}) — {t['requester'].mention}")

        if len(mq.queue) > 10:
            lines.append(f"…and {len(mq.queue) - 10} more.")

        await ctx.send(embed=self._embed(discord.Color.blurple(), "📋 Queue", "\n".join(lines)))

    @commands.command(name="loop")
    @is_music_dj()
    async def loop_cmd(self, ctx: commands.Context):
        """Toggle loop for the current track.
        Usage: !loop
        """
        mq = self._get_queue(ctx.guild.id)
        mq.loop = not mq.loop
        state = "🔁 **Loop ON**" if mq.loop else "➡️ **Loop OFF**"
        await ctx.send(embed=self._embed(discord.Color.blurple(), state, ""))

    @commands.command(name="volume", aliases=["vol"])
    @is_music_dj()
    async def volume(self, ctx: commands.Context, vol: int):
        """Set playback volume (0–200).
        Usage: !volume 80
        """
        vc = ctx.voice_client
        if not vc or not vc.source:
            return await ctx.send("Nothing is playing.")
        if not 0 <= vol <= 200:
            return await ctx.send("Volume must be between 0 and 200.")
        vc.source = discord.PCMVolumeTransformer(vc.source, volume=vol / 100)
        await ctx.send(embed=self._embed(discord.Color.green(), f"🔊 Volume set to {vol}%", ""))

    # ── error handling ────────────────────────────────────────────────────

    @play.error
    @skip.error
    @pause.error
    @resume.error
    @stop.error
    async def music_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(embed=self._embed(discord.Color.red(), "❌ No Permission",
                                             "You need the Music / DJ role."))
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
