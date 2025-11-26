import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os
import logging
import asyncpg
import asyncio
from datetime import datetime, timezone, timedelta

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
from reminder import ReminderManager

# --- Bot Configuration ---
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

class SupporterCommandTree(discord.app_commands.CommandTree):
    """A custom CommandTree to reliably count command usage in the database."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.command is not None:
            bot_instance = interaction.client
            if bot_instance.pool:
                try:
                    # Increment command counter in the database directly
                    await bot_instance.pool.execute(
                        """
                        INSERT INTO public.bot_stats (bot_id, commands_used) VALUES ($1, 1)
                        ON CONFLICT (bot_id) DO UPDATE SET
                        commands_used = public.bot_stats.commands_used + 1,
                        last_updated = NOW();
                        """,
                        str(bot_instance.user.id),
                    )
                    log.info(
                        f"📊 Command used: /{interaction.command.name} by {interaction.user}. DB counter incremented."
                    )
                except Exception as e:
                    log.error(f"Failed to increment command counter in DB: {e}")
        return True

class SupporterBot(commands.Bot):
    """A custom bot class to hold our database connection and managers."""

    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            tree_cls=SupporterCommandTree,
        )
        self.pool = None

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
        self.reminder_manager = ReminderManager(self, self.pool)

        await self.datetime_manager.start()
        await self.notext_manager.start()
        await self.level_manager.start()
        await self.youtube_manager.start()
        await self.reminder_manager.start()

        # 3. Register slash commands from all managers
        self.datetime_manager.register_commands()
        self.notext_manager.register_commands()
        self.help_manager.register_commands()
        self.owner_manager.register_commands()
        self.level_manager.register_commands()
        self.youtube_manager.register_commands()
        self.reminder_manager.register_commands()

        # 4. Start the stats update loop
        self.update_stats_task.start()

        log.info("All managers have been initialized.")

    async def update_stats_once(self) -> bool:
        """
        Periodically updates server and user counts. Command count is handled incrementally elsewhere.
        """
        if self.pool is None or not self.is_ready():
            return False

        server_count = len(self.guilds)
        user_count = sum(
            guild.member_count for guild in self.guilds if guild.member_count
        )

        log.info("=" * 60)
        log.info("📊 STATS UPDATE TRIGGERED")
        log.info(f"   Servers: {server_count}")
        log.info(f"   Users: {user_count}")
        log.info("=" * 60)

        query = """
            INSERT INTO public.bot_stats (bot_id, server_count, user_count, last_updated)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (bot_id) DO UPDATE SET
                server_count = $2,
                user_count = $3,
                last_updated = NOW();
        """
        try:
            await self.pool.execute(
                query,
                str(self.user.id),
                server_count,
                user_count,
            )
            log.info("✅ Server/User stats successfully written to database")

            verify = await self.pool.fetchrow(
                "SELECT * FROM public.bot_stats WHERE bot_id = $1", str(self.user.id)
            )
            if verify:
                log.info(
                    f"✅ Verification: DB now shows {verify['server_count']} servers, "
                    f"{verify['user_count']} users, {verify['commands_used']} total commands"
                )
            else:
                log.error("❌ Verification failed: No row found in database!")

            return True

        except Exception as e:
            log.error(f"❌ Failed to update bot stats in DB: {e}", exc_info=True)
            return False

    @tasks.loop(minutes=2)
    async def update_stats_task(self):
        """Periodically updates the bot's stats in the database."""
        await self.update_stats_once()

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
            await bot.pool.execute(
                """
                INSERT INTO public.bot_stats (bot_id, server_count, user_count, commands_used, last_updated)
                VALUES ($1, $2, $3, 0, NOW())
                ON CONFLICT (bot_id) DO NOTHING
                """,
                str(bot.user.id),
                len(bot.guilds),
                sum(
                    g.member_count for g in bot.guilds if g.member_count
                ), 
            )
            log.info("✅ Verified bot_stats table entry.")
        except Exception as e:
            log.error(f"⚠️ Error initializing/verifying bot_stats: {e}")

    # Sync all guilds to database on startup to ensure dashboard has them
    await sync_all_guilds_to_database()

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
    """Track when bot joins a guild."""
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
            return

    try:
        async with bot.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO public.guild_settings (guild_id) 
                   VALUES ($1) 
                   ON CONFLICT (guild_id) DO NOTHING""",
                str(guild.id),
            )
        log.info(f"✅ Registered guild {guild.name} in database")
    except Exception as e:
        log.error(f"Error registering guild in database: {e}")


@bot.event
async def on_guild_remove(guild: discord.Guild):
    """Track when bot leaves a guild and mark it as inactive."""
    log.info(f"👋 Left server: {guild.name} (ID: {guild.id})")

    try:
        async with bot.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM public.guild_settings WHERE guild_id = $1",
                str(guild.id),
            )
        log.info(f"🗑️ De-registered guild {guild.name} from active list.")
    except Exception as e:
        log.error(f"Error de-registering guild from database: {e}")


async def sync_all_guilds_to_database():
    if not bot.pool:
        log.error("Cannot sync guilds: Database pool not initialized")
        return

    log.info(f"🔄 Syncing {len(bot.guilds)} guilds to database...")

    current_guild_ids = {str(g.id) for g in bot.guilds}

    async with bot.pool.acquire() as conn:
        db_guild_ids = {
            row["guild_id"]
            for row in await conn.fetch("SELECT guild_id FROM public.guild_settings")
        }

        guilds_to_add = current_guild_ids - db_guild_ids
        guilds_to_remove = db_guild_ids - current_guild_ids

        # Add new guilds
        if guilds_to_add:
            log.info(f"Found {len(guilds_to_add)} new guilds to register.")
            await conn.executemany(
                "INSERT INTO public.guild_settings (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING",
                [(gid,) for gid in guilds_to_add],
            )

        # Remove old/kicked guilds
        if guilds_to_remove:
            log.warning(
                f"Found {len(guilds_to_remove)} guilds to de-register (bot was removed)."
            )
            await conn.execute(
                "DELETE FROM public.guild_settings WHERE guild_id = ANY($1::TEXT[])",
                list(guilds_to_remove),
            )

    log.info("✅ Guild sync complete.")


@bot.tree.command(name="ping", description="Check if the bot is responsive.")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)

    # Get stats directly from database
    stats = await bot.pool.fetchrow(
        "SELECT * FROM public.bot_stats WHERE bot_id = $1", str(bot.user.id)
    )

    if stats:
        server_count = stats["server_count"]
        user_count = stats["user_count"]
        commands_used = stats["commands_used"]
    else:
        server_count = len(bot.guilds)
        user_count = sum(guild.member_count for guild in bot.guilds)
        commands_used = 0

    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot is online and responsive!",
        color=discord.Color.green(),
    )
    embed.add_field(name="Latency", value=f"{latency}ms")
    embed.add_field(name="Servers", value=f"{server_count}")
    embed.add_field(name="Total Users", value=f"{user_count}")
    embed.add_field(
        name="Commands Used (Total)", value=f"{commands_used}", inline=False
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

    updated = await bot.update_stats_once()
    if not updated:
        await interaction.followup.send(
            "⚠️ Could not update stats. Ensure the bot is ready and the database is reachable.",
            ephemeral=True,
        )
        return

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
    command_name = interaction.command.name if interaction.command else "unknown"
    log.error(f"Slash command error for '/{command_name}': {error}")
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
