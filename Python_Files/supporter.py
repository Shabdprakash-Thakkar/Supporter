# Python_Files/supporter.py

import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import logging
import asyncpg
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


class SupporterBot(commands.Bot):
    """A custom bot class to hold our database connection and managers."""

    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.pool = None

    async def setup_hook(self):
        """This function is called once the bot is ready, before it connects to Discord."""
        log.info("Bot is setting up...")

        # 1. Connect to the PostgreSQL database
        try:
            self.pool = await asyncpg.create_pool(DATABASE_URL, max_size=20)
            log.info("✅ Successfully connected to the PostgreSQL database.")
        except Exception as e:
            log.critical(f"❌ CRITICAL: Could not connect to the database: {e}")
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

        log.info("All managers have been initialized.")


bot = SupporterBot()


@bot.event
async def on_ready():
    """Event that runs when the bot is fully connected and ready."""
    log.info("=" * 50)
    log.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

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


# --- GENERAL COMMANDS ---
@bot.tree.command(
    name="g2-show-config",
    description="Show the current bot configuration for this server.",
)
@discord.app_commands.checks.has_permissions(manage_guild=True)
async def show_config(interaction: discord.Interaction):
    """Displays a comprehensive summary of all bot configurations for the server."""
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    guild = interaction.guild

    # Create main embed
    embed = discord.Embed(
        title=f"🤖 Bot Configuration",
        description=f"**Server:** {guild.name}\n**Server ID:** `{guild_id}`",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)

    async with bot.pool.acquire() as conn:
        # ====================== LEVELING SYSTEM ======================
        level_notify_ch_id = await conn.fetchval(
            "SELECT channel_id FROM public.level_notify_channel WHERE guild_id = $1",
            guild_id,
        )
        auto_reset_config = await conn.fetchrow(
            "SELECT days, last_reset FROM public.auto_reset WHERE guild_id = $1", 
            guild_id
        )
        level_rewards = await conn.fetch(
            "SELECT level, role_id, role_name FROM public.level_roles WHERE guild_id = $1 ORDER BY level ASC",
            guild_id,
        )
        total_users = await conn.fetchval(
            "SELECT COUNT(*) FROM public.users WHERE guild_id = $1", guild_id
        )
        
        # Build leveling config text
        level_text = []
        
        if level_notify_ch_id:
            channel = guild.get_channel(int(level_notify_ch_id))
            level_text.append(f"📢 **Notifications:** {channel.mention if channel else '❌ Channel Deleted'}")
        else:
            level_text.append("📢 **Notifications:** ⚠️ Not Configured")
        
        if auto_reset_config:
            days = auto_reset_config['days']
            last_reset = auto_reset_config['last_reset']
            next_reset = last_reset + timedelta(days=days)
            level_text.append(f"♻️ **Auto-Reset:** Every {days} day(s)")
            level_text.append(f"📅 **Next Reset:** {discord.utils.format_dt(next_reset, 'R')}")
        else:
            level_text.append("♻️ **Auto-Reset:** ⚠️ Disabled")
        
        level_text.append(f"👥 **Tracked Users:** {total_users or 0}")
        
        if level_rewards:
            role_list = []
            for reward in level_rewards[:5]:  # Show first 5
                role = guild.get_role(int(reward['role_id']))
                if role:
                    role_list.append(f"  • Level {reward['level']} → {role.mention}")
                else:
                    role_list.append(f"  • Level {reward['level']} → ❌ `{reward['role_name']}` (Deleted)")
            
            if len(level_rewards) > 5:
                role_list.append(f"  *...and {len(level_rewards) - 5} more*")
            
            level_text.append(f"🏆 **Role Rewards:** {len(level_rewards)} configured\n" + "\n".join(role_list))
        else:
            level_text.append("🏆 **Role Rewards:** ⚠️ None Configured")
        
        embed.add_field(
            name="📊 Leveling System", 
            value="\n".join(level_text) if level_text else "⚠️ Not Configured",
            inline=False
        )

        # ====================== YOUTUBE NOTIFICATIONS ======================
        yt_configs = await conn.fetch(
            "SELECT yt_channel_id, yt_channel_name, target_channel_id, mention_role_id, mention_role_name, is_enabled FROM public.youtube_notification_config WHERE guild_id = $1",
            guild_id,
        )
        
        if yt_configs:
            yt_text = []
            for idx, cfg in enumerate(yt_configs[:3], 1):  # Show first 3
                channel = guild.get_channel(int(cfg['target_channel_id']))
                role = guild.get_role(int(cfg['mention_role_id'])) if cfg['mention_role_id'] else None
                
                status = "✅" if cfg['is_enabled'] else "🔴"
                channel_name = cfg['yt_channel_name'] or "Unknown Channel"
                
                yt_text.append(f"{status} **{channel_name}**")
                yt_text.append(f"  📺 Channel ID: `{cfg['yt_channel_id']}`")
                yt_text.append(f"  📍 Posts to: {channel.mention if channel else '❌ Deleted'}")
                if role:
                    yt_text.append(f"  🔔 Mentions: {role.mention}")
                yt_text.append("")  # Blank line
            
            if len(yt_configs) > 3:
                yt_text.append(f"*...and {len(yt_configs) - 3} more channels*")
            
            embed.add_field(
                name=f"📢 YouTube Notifications ({len(yt_configs)} channels)",
                value="\n".join(yt_text) or "None",
                inline=False
            )
        else:
            embed.add_field(
                name="📢 YouTube Notifications",
                value="⚠️ No YouTube channels configured\nUse `/y2-setup-youtube-notifications` to add one",
                inline=False
            )

        # ====================== CHANNEL RESTRICTIONS ======================
        # Media-Only Channels
        no_text_channels = await conn.fetch(
            "SELECT channel_id, redirect_channel_id FROM public.no_text_channels WHERE guild_id = $1",
            guild_id,
        )
        
        # Text-Only Channels
        text_only_channels = await conn.fetch(
            "SELECT channel_id, redirect_channel_id FROM public.text_only_channels WHERE guild_id = $1",
            guild_id,
        )
        
        # No Discord Links
        no_discord_links = await conn.fetch(
            "SELECT channel_id FROM public.no_discord_links_channels WHERE guild_id = $1",
            guild_id,
        )
        
        # No Links (All)
        no_links = await conn.fetch(
            "SELECT channel_id FROM public.no_links_channels WHERE guild_id = $1",
            guild_id,
        )
        
        # Bypass Roles
        bypass_roles = await conn.fetch(
            "SELECT role_id, role_name FROM public.bypass_roles WHERE guild_id = $1",
            guild_id,
        )
        
        restriction_text = []
        
        if no_text_channels:
            restriction_text.append(f"🖼️ **Media-Only:** {len(no_text_channels)} channel(s)")
            for ch in no_text_channels[:2]:
                channel = guild.get_channel(int(ch['channel_id']))
                redirect = guild.get_channel(int(ch['redirect_channel_id']))
                if channel and redirect:
                    restriction_text.append(f"  • {channel.mention} → redirects to {redirect.mention}")
            if len(no_text_channels) > 2:
                restriction_text.append(f"  *...and {len(no_text_channels) - 2} more*")
        
        if text_only_channels:
            restriction_text.append(f"📝 **Text-Only:** {len(text_only_channels)} channel(s)")
            for ch in text_only_channels[:2]:
                channel = guild.get_channel(int(ch['channel_id']))
                redirect = guild.get_channel(int(ch['redirect_channel_id']))
                if channel and redirect:
                    restriction_text.append(f"  • {channel.mention} → redirects to {redirect.mention}")
            if len(text_only_channels) > 2:
                restriction_text.append(f"  *...and {len(text_only_channels) - 2} more*")
        
        if no_discord_links:
            restriction_text.append(f"🔗 **No Discord Links:** {len(no_discord_links)} channel(s)")
            for ch in no_discord_links[:2]:
                channel = guild.get_channel(int(ch['channel_id']))
                if channel:
                    restriction_text.append(f"  • {channel.mention}")
            if len(no_discord_links) > 2:
                restriction_text.append(f"  *...and {len(no_discord_links) - 2} more*")
        
        if no_links:
            restriction_text.append(f"🚫 **No Links (All):** {len(no_links)} channel(s)")
            for ch in no_links[:2]:
                channel = guild.get_channel(int(ch['channel_id']))
                if channel:
                    restriction_text.append(f"  • {channel.mention}")
            if len(no_links) > 2:
                restriction_text.append(f"  *...and {len(no_links) - 2} more*")
        
        if bypass_roles:
            restriction_text.append(f"\n🛡️ **Bypass Roles:** {len(bypass_roles)}")
            for r in bypass_roles[:3]:
                role = guild.get_role(int(r['role_id']))
                if role:
                    restriction_text.append(f"  • {role.mention}")
                else:
                    restriction_text.append(f"  • ❌ `{r['role_name']}` (Deleted)")
            if len(bypass_roles) > 3:
                restriction_text.append(f"  *...and {len(bypass_roles) - 3} more*")
        
        if restriction_text:
            embed.add_field(
                name="🚫 Channel Restrictions",
                value="\n".join(restriction_text),
                inline=False
            )
        else:
            embed.add_field(
                name="🚫 Channel Restrictions",
                value="⚠️ No restrictions configured",
                inline=False
            )

        # ====================== TIME CHANNELS ======================
        time_cfg = await conn.fetchrow(
            "SELECT date_channel_id, india_channel_id, japan_channel_id FROM public.time_channel_config WHERE guild_id = $1",
            guild_id,
        )
        
        if time_cfg:
            date_ch = guild.get_channel(int(time_cfg['date_channel_id']))
            india_ch = guild.get_channel(int(time_cfg['india_channel_id']))
            japan_ch = guild.get_channel(int(time_cfg['japan_channel_id']))
            
            time_text = []
            if date_ch:
                time_text.append(f"📅 **Date Channel:** {date_ch.mention}")
            if india_ch:
                time_text.append(f"🇮🇳 **India Time:** {india_ch.mention}")
            if japan_ch:
                time_text.append(f"🇯🇵 **Japan Time:** {japan_ch.mention}")
            
            time_text.append("\n⏰ *Updates every 10 minutes*")
            
            embed.add_field(
                name="⏰ Time Channels",
                value="\n".join(time_text),
                inline=False
            )

    # Footer with helpful info
    embed.set_footer(
        text=f"Use /g1-help to see all commands • Configuration as of",
        icon_url=bot.user.avatar.url if bot.user.avatar else None
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
