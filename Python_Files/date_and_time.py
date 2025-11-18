# Python_Files/date_and_time.py

import discord
from discord.ext import tasks, commands
import pytz
from datetime import datetime, timedelta
import asyncpg
import logging
import asyncio

log = logging.getLogger(__name__)


class DateTimeManager:
    def __init__(self, bot: commands.Bot, pool: asyncpg.Pool):
        self.bot = bot
        self.pool = pool
        self.server_configs = {}
        log.info("Date and Time system initialized.")
        self.bot.add_listener(self.on_ready, "on_ready")

    async def _load_configs_from_db(self):
        """Loads all time configurations from the database into a local cache."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM public.time_channel_config;")
            for row in rows:
                self.server_configs[int(row["guild_id"])] = dict(row)
        log.info(f"Loaded {len(self.server_configs)} time configurations.")

    async def start(self):
        await self._load_configs_from_db()
        self.update_time_channels.start()
        self.update_date_daily.start()

    async def on_ready(self):
        await asyncio.sleep(2)  # give cache time
        await self.update_date_channel()

    # -------------------- DATE MANAGEMENT --------------------

    async def update_date_channel(self):
        tz_india = pytz.timezone("Asia/Kolkata")
        date_str = datetime.now(tz_india).strftime("%d %B, %Y")
        new_name = f"📅 {date_str}"

        log.info(f"Checking date channels to update to: {new_name}")

        for guild_id, config in self.server_configs.items():
            # ✨ NEW: Check if the feature is enabled for this guild
            if not config.get("is_enabled"):
                continue

            try:
                channel_id = config.get("date_channel_id")
                if not channel_id:
                    continue

                channel = self.bot.get_channel(int(channel_id))
                if channel and channel.name != new_name:
                    await channel.edit(name=new_name)
            except discord.Forbidden:
                log.warning(f"No permission to edit date channel in guild {guild_id}.")
            except Exception as e:
                log.error(f"Error updating date channel for guild {guild_id}: {e}")

    @tasks.loop(hours=24)
    async def update_date_daily(self):
        await self.update_date_channel()

    @update_date_daily.before_loop
    async def before_update_date_daily(self):
        await self.bot.wait_until_ready()
        tz_india = pytz.timezone("Asia/Kolkata")
        now = datetime.now(tz_india)
        next_midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        seconds_to_wait = (next_midnight - now).total_seconds()
        log.info(
            f"Aligning date updates. Waiting {seconds_to_wait:.0f} seconds until next run."
        )
        await asyncio.sleep(seconds_to_wait)
        log.info("Date alignment complete. Starting daily date loop.")

    # -------------------- TIME MANAGEMENT --------------------

    @tasks.loop(minutes=10)
    async def update_time_channels(self):
        log.info("Checking time channels...")

        tz_india = pytz.timezone("Asia/Kolkata")
        tz_japan = pytz.timezone("Asia/Tokyo")

        india_time = datetime.now(tz_india).strftime("%H:%M")
        japan_time = datetime.now(tz_japan).strftime("%H:%M")

        india_name = f"🇮🇳 IST {india_time}"
        japan_name = f"🇯🇵 JST {japan_time}"

        for guild_id, config in self.server_configs.items():
            # ✨ NEW: Check if the feature is enabled for this guild
            if not config.get("is_enabled"):
                continue

            try:
                # India
                india_channel_id = config.get("india_channel_id")
                if india_channel_id:
                    india_channel = self.bot.get_channel(int(india_channel_id))
                    if india_channel and india_channel.name != india_name:
                        await india_channel.edit(name=india_name)

                # Japan
                japan_channel_id = config.get("japan_channel_id")
                if japan_channel_id:
                    japan_channel = self.bot.get_channel(int(japan_channel_id))
                    if japan_channel and japan_channel.name != japan_name:
                        await japan_channel.edit(name=japan_name)

            except discord.Forbidden:
                log.warning(f"No permission to edit time channels in guild {guild_id}.")
            except Exception as e:
                log.error(f"Error updating time channels for guild {guild_id}: {e}")

    @update_time_channels.before_loop
    async def before_update_time_channels(self):
        await self.bot.wait_until_ready()
        now = datetime.now()
        minutes_to_wait = 10 - (now.minute % 10)
        seconds_to_wait = (minutes_to_wait * 60) - now.second
        log.info(
            f"Aligning time updates. Waiting {seconds_to_wait:.0f} seconds until first run."
        )
        await asyncio.sleep(seconds_to_wait)
        log.info("Time alignment complete. Starting 10-minute loop.")

    # -------------------- SLASH COMMAND --------------------

    def register_commands(self):

        @self.bot.tree.command(
            name="t1-setup-time-channels",
            description="Set up and enable date, India time, and Japan time channels.",
        )
        @discord.app_commands.checks.has_permissions(manage_channels=True)
        @discord.app_commands.describe(
            date_channel="Voice channel for current date.",
            india_channel="Voice channel for India time (IST).",
            japan_channel="Voice channel for Japan time (JST).",
        )
        async def setup_time_channels(
            interaction: discord.Interaction,
            date_channel: discord.VoiceChannel,
            india_channel: discord.VoiceChannel,
            japan_channel: discord.VoiceChannel,
        ):
            await interaction.response.defer(ephemeral=True)
            guild_id = interaction.guild_id

            # ✨ UPDATED: Query now sets is_enabled to TRUE on setup.
            query = """
                INSERT INTO public.time_channel_config 
                  (guild_id, guild_name, date_channel_id, india_channel_id, japan_channel_id, is_enabled, updated_at)
                VALUES ($1, $2, $3, $4, $5, TRUE, NOW())
                ON CONFLICT (guild_id) DO UPDATE SET
                  guild_name = EXCLUDED.guild_name,
                  date_channel_id = EXCLUDED.date_channel_id,
                  india_channel_id = EXCLUDED.india_channel_id,
                  japan_channel_id = EXCLUDED.japan_channel_id,
                  is_enabled = TRUE,
                  updated_at = NOW();
            """

            async with self.pool.acquire() as conn:
                await conn.execute(
                    query,
                    str(guild_id),
                    interaction.guild.name,
                    str(date_channel.id),
                    str(india_channel.id),
                    str(japan_channel.id),
                )

            # Update local cache
            self.server_configs[guild_id] = {
                "guild_id": str(guild_id),
                "date_channel_id": str(date_channel.id),
                "india_channel_id": str(india_channel.id),
                "japan_channel_id": str(japan_channel.id),
                "is_enabled": True,
            }

            # Manually trigger an update right away
            await self.update_date_channel()
            # The time channels will update on their next 10-minute interval

            await interaction.followup.send(
                f"✅ Time channels configured and enabled!\n"
                f"📅 Date: {date_channel.mention}\n"
                f"🇮🇳 IST: {india_channel.mention}\n"
                f"🇯🇵 JST: {japan_channel.mention}\n\n"
                f"You can manage these settings from the web dashboard.",
                ephemeral=True,
            )

        log.info("Date & Time commands registered.")
