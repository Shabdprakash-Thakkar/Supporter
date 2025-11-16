# Python_Files/supporter.py

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os
import logging
import asyncpg
import asyncio
from datetime import datetime, timezone, timedelta

# --- Basic Setup ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "Data_Files")
load_dotenv(os.path.join(DATA_DIR, ".env"))

logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] [%(name)s] [%(levelname)s]  %(message)s"
)
log = logging.getLogger(__name__)

# --- Import All Feature Managers ---
from date_and_time import DateTimeManager
from no_text import NoTextManager
from help import HelpManager
from owner_actions import OwnerActionsManager
from level import LevelManager
from youtube_notification import YouTubeManager

# --- Bot Configuration ---
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True


# --- START: NEW RELIABLE FIX ---
class SupporterCommandTree(discord.app_commands.CommandTree):
    """A custom CommandTree to reliably count command usage."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # This function runs for EVERY slash command before its code is executed.
        if interaction.command is not None:
            # The 'bot' instance is available via the interaction object.
            bot_instance = interaction.client
            bot_instance.commands_used_session += 1
            log.info(
                f"📊 Command used: /{interaction.command.name} by {interaction.user} in {interaction.guild.name} | Session total: {bot_instance.commands_used_session}"
            )
        # Always return True to allow the command to proceed.
        return True


# --- END: NEW RELIABLE FIX ---


class SupporterBot(commands.Bot):
    """A custom bot class to hold our database connection and managers."""

    def __init__(self):
        # --- START: MODIFIED SECTION ---
        # Instruct the bot to use our custom command tree class.
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            tree_cls=SupporterCommandTree,
        )
        # --- END: MODIFIED SECTION ---
        self.pool = None
        # STATS TRACKING
        self.commands_used_session = 0
        self.total_commands_db = 0

    async def setup_hook(self):
        """This function is called once the bot is ready, before it connects to Discord."""
        log.info("Bot is setting up...")

        # 1. Connect to the PostgreSQL database
        try:
            self.pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=5,
                max_size=20,
                max_inactive_connection_lifetime=300,
                command_timeout=60,
                max_queries=50000,
                statement_cache_size=0,
            )
            log.info("✅ Successfully connected to the PostgreSQL database.")
            log.info(f"   Pool settings: min=5, max=20, timeout=60s")
            log.info(f"   Connection mode: Transaction (port 6543)")
            log.info(f"   ⚡ Statement cache: DISABLED (pgbouncer compatible)")
        except Exception as e:
            log.critical(f"❌ CRITICAL: Could not connect to the database: {e}")
            log.critical(
                "   Make sure you're using port 6543 (Transaction mode) not 5432 (Session mode)!"
            )
            await self.close()
            return

        # 2. Initialize and start all managers
        log.info("Initializing feature managers...")
        self.datetime_manager = DateTimeManager(self, self.pool)
        self.notext_manager = NoTextManager(self, self.pool)
        self.help_manager = HelpManager(self)
        self.owner_manager = OwnerActionsManager(self, self.pool)
        self.level_manager = LevelManager(self, self.pool)
        self.youtube_manager = YouTubeManager(self, self.pool)

        await self.datetime_manager.start()
        await self.notext_manager.start()
        await self.level_manager.start()
        await self.youtube_manager.start()

        # 3. Register slash commands from all managers
        self.datetime_manager.register_commands()
        self.notext_manager.register_commands()
        self.help_manager.register_commands()
        self.owner_manager.register_commands()
        self.level_manager.register_commands()
        self.youtube_manager.register_commands()

        # 4. Start the stats update loop
        self.update_stats_task.start()

        log.info("All managers have been initialized.")

    @tasks.loop(minutes=2)
    async def update_stats_task(self):
        """Periodically updates the bot's stats in the database."""
        if self.pool is None or not self.is_ready() or self.commands_used_session == 0:
            if self.is_ready() and self.commands_used_session == 0:
                log.info("📊 Stats update skipped - no new commands in this session.")
            return

        server_count = len(self.guilds)
        user_count = sum(guild.member_count for guild in self.guilds)
        current_command_total = self.total_commands_db + self.commands_used_session

        log.info("=" * 60)
        log.info("📊 STATS UPDATE TRIGGERED")
        log.info(f"   Servers: {server_count}")
        log.info(f"   Users: {user_count}")
        log.info(f"   Commands (DB): {self.total_commands_db}")
        log.info(f"   Commands (Session): {self.commands_used_session}")
        log.info(f"   Commands (Total): {current_command_total}")
        log.info("=" * 60)

        query = """
            INSERT INTO public.bot_stats (bot_id, server_count, user_count, commands_used, last_updated)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (bot_id) DO UPDATE SET
                server_count = $2,
                user_count = $3,
                commands_used = $4,
                last_updated = NOW();
        """
        try:
            await self.pool.execute(
                query,
                str(self.user.id),
                server_count,
                user_count,
                current_command_total,
            )
            log.info("✅ Stats successfully written to database")

            self.total_commands_db = current_command_total
            self.commands_used_session = 0
            log.info(
                f"   In-memory stats synced: total_commands_db={self.total_commands_db}, commands_used_session={self.commands_used_session}"
            )

            verify = await self.pool.fetchrow(
                "SELECT * FROM public.bot_stats WHERE bot_id = $1", str(self.user.id)
            )
            if verify:
                log.info(
                    f"✅ Verification: DB now shows {verify['commands_used']} commands"
                )
            else:
                log.error("❌ Verification failed: No row found in database!")

        except Exception as e:
            log.error(f"❌ Failed to update bot stats in DB: {e}", exc_info=True)
            log.error(
                f"   Query attempted with values: bot_id={self.user.id}, servers={server_count}, users={user_count}, commands={current_command_total}"
            )

    @update_stats_task.before_loop
    async def before_update_stats_task(self):
        await self.wait_until_ready()
        now = datetime.now()
        minutes_to_wait = 2 - (now.minute % 2)
        seconds_to_wait = (minutes_to_wait * 60) - now.second

        target_minute = (now.minute + minutes_to_wait) % 60
        log.info(
            f"Aligning stats update. Waiting {seconds_to_wait:.1f} seconds for first run at minute :{target_minute:02d}."
        )
        await asyncio.sleep(seconds_to_wait)


bot = SupporterBot()


@bot.event
async def on_ready():
    """Event that runs when the bot is fully connected and ready."""
    log.info("=" * 50)
    log.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

    if bot.pool:
        try:
            bot.total_commands_db = (
                await bot.pool.fetchval(
                    "SELECT commands_used FROM public.bot_stats WHERE bot_id = $1",
                    str(bot.user.id),
                )
                or 0
            )
            log.info(
                f"📊 Loaded initial command count from DB: {bot.total_commands_db}"
            )
        except Exception as e:
            log.warning(f"⚠️ Could not load command count (table might be empty): {e}")
            bot.total_commands_db = 0

            try:
                await bot.pool.execute(
                    """
                    INSERT INTO public.bot_stats (bot_id, server_count, user_count, commands_used, last_updated)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (bot_id) DO NOTHING
                    """,
                    str(bot.user.id),
                    len(bot.guilds),
                    sum(guild.member_count for guild in bot.guilds),
                    0,
                )
                log.info("✅ Initialized bot_stats table with default values")
            except Exception as init_error:
                log.error(f"❌ Failed to initialize bot_stats: {init_error}")

    try:
        synced = await bot.tree.sync()
        log.info(f"✅ Synced {len(synced)} slash commands globally.")
    except Exception as e:
        log.error(f"❌ Failed to sync slash commands: {e}")

    log.info(f"🚀 Bot is connected to {len(bot.guilds)} server(s):")
    for guild in bot.guilds:
        log.info(f"   - {guild.name} (ID: {guild.id})")
    log.info("=" * 50)
    log.info("✅ Bot is fully ready and operational!")


@bot.event
async def on_guild_join(guild: discord.Guild):
    log.info(f"🔥 Joined a new server: {guild.name} (ID: {guild.id})")
    if await bot.owner_manager.is_guild_banned(guild.id):
        log.warning(f"🚫 Bot joined banned server {guild.name}. Leaving immediately.")
        try:
            if guild.owner:
                await guild.owner.send(
                    "This bot is not permitted in this server and has been removed."
                )
        except discord.Forbidden:
            log.warning("Could not notify server owner about the ban.")
        finally:
            await guild.leave()


@bot.tree.command(name="ping", description="Check if the bot is responsive.")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)

    server_count = len(bot.guilds)
    user_count = sum(guild.member_count for guild in bot.guilds)
    current_command_total = bot.total_commands_db + bot.commands_used_session

    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot is online and responsive!",
        color=discord.Color.green(),
    )
    embed.add_field(name="Latency", value=f"{latency}ms")
    embed.add_field(name="Servers", value=f"{server_count}")
    embed.add_field(name="Total Users", value=f"{user_count}")
    embed.add_field(
        name="Commands Used (Session)",
        value=f"{bot.commands_used_session}",
        inline=False,
    )
    embed.add_field(
        name="Commands Used (Total)", value=f"{current_command_total}", inline=False
    )
    embed.set_footer(text="Stats update every 2 minutes")

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="force-stats-update",
    description="[OWNER] Force update bot stats to database immediately.",
)
async def force_stats_update(interaction: discord.Interaction):
    if not await bot.is_owner(interaction.user):
        await interaction.response.send_message(
            "❌ This command is only for the bot owner.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    await bot.update_stats_task.coro(bot.update_stats_task.__self__)

    updated_stats = await bot.pool.fetchrow(
        "SELECT * FROM public.bot_stats WHERE bot_id = $1", str(bot.user.id)
    )

    if updated_stats:
        embed = discord.Embed(
            title="✅ Stats Force Updated!",
            color=discord.Color.green(),
        )
        embed.add_field(name="Servers", value=str(updated_stats["server_count"]))
        embed.add_field(name="Users", value=str(updated_stats["user_count"]))
        embed.add_field(name="Commands Used", value=str(updated_stats["commands_used"]))
        embed.add_field(name="Session Commands", value="0 (just reset)", inline=False)
        embed.set_footer(text="Database updated successfully!")
        await interaction.followup.send(embed=embed, ephemeral=True)
        log.info(f"🔄 Stats manually updated by {interaction.user}")
    else:
        await interaction.followup.send(
            "❌ Error updating stats: Could not verify the update.", ephemeral=True
        )


@bot.tree.command(
    name="g2-show-config",
    description="Show the current bot configuration for this server.",
)
@discord.app_commands.checks.has_permissions(manage_guild=True)
async def show_config(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    guild = interaction.guild

    embed = discord.Embed(
        title=f"🤖 Bot Configuration",
        description=f"**Server:** {guild.name}\n**Server ID:** `{guild_id}`",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)

    async with bot.pool.acquire() as conn:
        level_notify_ch_id = await conn.fetchval(
            "SELECT channel_id FROM public.level_notify_channel WHERE guild_id = $1",
            guild_id,
        )
        auto_reset_config = await conn.fetchrow(
            "SELECT days, last_reset FROM public.auto_reset WHERE guild_id = $1",
            guild_id,
        )
        level_rewards = await conn.fetch(
            "SELECT level, role_id, role_name FROM public.level_roles WHERE guild_id = $1 ORDER BY level ASC",
            guild_id,
        )
        total_users = await conn.fetchval(
            "SELECT COUNT(*) FROM public.users WHERE guild_id = $1", guild_id
        )

        level_text = []

        if level_notify_ch_id:
            channel = guild.get_channel(int(level_notify_ch_id))
            level_text.append(
                f"📢 **Notifications:** {channel.mention if channel else '❌ Channel Deleted'}"
            )
        else:
            level_text.append("📢 **Notifications:** ⚠️ Not Configured")

        if auto_reset_config:
            days = auto_reset_config["days"]
            last_reset = auto_reset_config["last_reset"]
            next_reset = last_reset + timedelta(days=days)
            level_text.append(f"♻️ **Auto-Reset:** Every {days} day(s)")
            level_text.append(
                f"📅 **Next Reset:** {discord.utils.format_dt(next_reset, 'R')}"
            )
        else:
            level_text.append("♻️ **Auto-Reset:** ⚠️ Disabled")

        level_text.append(f"👥 **Tracked Users:** {total_users or 0}")

        if level_rewards:
            role_list = []
            for reward in level_rewards[:5]:
                role = guild.get_role(int(reward["role_id"]))
                if role:
                    role_list.append(f"  • Level {reward['level']} → {role.mention}")
                else:
                    role_list.append(
                        f"  • Level {reward['level']} → ❌ `{reward['role_name']}` (Deleted)"
                    )

            if len(level_rewards) > 5:
                role_list.append(f"  *...and {len(level_rewards) - 5} more*")

            level_text.append(
                f"🏆 **Role Rewards:** {len(level_rewards)} configured\n"
                + "\n".join(role_list)
            )
        else:
            level_text.append("🏆 **Role Rewards:** ⚠️ None Configured")

        embed.add_field(
            name="📊 Leveling System",
            value="\n".join(level_text) if level_text else "⚠️ Not Configured",
            inline=False,
        )

    embed.set_footer(
        text=f"Use /g1-help to see all commands • Configuration as of",
        icon_url=bot.user.avatar.url if bot.user.avatar else None,
    )

    await interaction.followup.send(embed=embed)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: discord.app_commands.AppCommandError
):
    log.error(f"Slash command error for '/{interaction.command.name}': {error}")
    message = "❌ An unexpected error occurred. Please try again later."
    if isinstance(error, discord.app_commands.MissingPermissions):
        message = "🚫 You do not have the required permissions to run this command."
    elif isinstance(error, discord.app_commands.CheckFailure):
        message = "🚫 You are not allowed to use this command."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


def run_bot():
    """Checks for necessary tokens and runs the bot."""
    if not TOKEN:
        log.critical("❌ Error: DISCORD_TOKEN not found in .env file!")
        return
    if not DATABASE_URL:
        log.critical("❌ Error: DATABASE_URL not found in .env file!")
        return
    bot.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    run_bot()
