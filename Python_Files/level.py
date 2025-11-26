import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta
import asyncpg
import logging
import time

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
SETTINGS_CACHE_DURATION = 300  # 5 minutes in seconds


class LevelManager:
    """Manages all leveling, XP, and role-reward logic for the bot."""

    def __init__(self, bot: commands.Bot, pool: asyncpg.Pool):
        self.bot = bot
        self.pool = pool
        self.voice_sessions = {}
        self.user_cache = {}
        self.message_cooldowns = {}
        self.settings_cache = {}  # Cache for guild-specific settings

    async def start(self):
        """Starts the manager by adding event listeners and loops."""
        self.bot.add_listener(self.on_message, "on_message")
        self.bot.add_listener(self.on_voice_state_update, "on_voice_state_update")
        self.reset_loop.start()
        self.cleanup_cooldowns.start()
        log.info("Leveling system has been initialized (Dynamic Settings Mode).")

    # --- Settings Management ---
    async def get_guild_settings(self, guild_id: int) -> dict:
        """
        Retrieves leveling settings for a guild, using a cache.
        If settings don't exist, creates them with default values.
        """
        now = time.time()

        # Check cache first
        if guild_id in self.settings_cache:
            cached_settings, timestamp = self.settings_cache[guild_id]
            if now - timestamp < SETTINGS_CACHE_DURATION:
                return cached_settings

        async with self.pool.acquire() as conn:
            # Attempt to fetch settings
            settings_record = await conn.fetchrow(
                "SELECT * FROM public.guild_settings WHERE guild_id = $1", str(guild_id)
            )

            # If no settings exist, create them with NEW defaults
            if not settings_record:
                await conn.execute(
                    """INSERT INTO public.guild_settings 
                        (guild_id, xp_per_message, xp_per_image, xp_per_minute_in_voice, voice_xp_limit) 
                        VALUES ($1, 5, 10, 15, 1500) 
                        ON CONFLICT (guild_id) DO NOTHING""",
                    str(guild_id),
                )
                # Re-fetch to get the newly created default settings
                settings_record = await conn.fetchrow(
                    "SELECT * FROM public.guild_settings WHERE guild_id = $1",
                    str(guild_id),
                )

        settings_dict = dict(settings_record) if settings_record else {
                "xp_per_message": 5,
                "xp_per_image": 10,
                "xp_per_minute_in_voice": 15,
                "voice_xp_limit": 1500,
        }    

        self.settings_cache[guild_id] = (settings_dict, now)
        return settings_dict

    # --- Database Utilities ---

    async def get_user(self, guild_id: int, user_id: int) -> dict:
        key = (guild_id, user_id)
        if user_data := self.user_cache.get(key):
            return user_data

        async with self.pool.acquire() as conn:
            user_record = await conn.fetchrow(
                "SELECT * FROM public.users WHERE guild_id = $1 AND user_id = $2",
                str(guild_id),
                str(user_id),
            )

        if user_record:
            user_dict = dict(user_record)
            self.user_cache[key] = user_dict
            return user_dict
        return await self.create_user(guild_id, user_id)

    async def create_user(self, guild_id: int, user_id: int) -> dict:
        guild = self.bot.get_guild(guild_id)
        member = guild.get_member(user_id) if guild else None
        guild_name = guild.name if guild else "Unknown Guild"
        user_name = member.name if member else "Unknown User"

        query = "INSERT INTO public.users (guild_id, user_id, guild_name, username) VALUES ($1, $2, $3, $4) ON CONFLICT (guild_id, user_id) DO UPDATE SET guild_name = $3, username = $4"
        await self.pool.execute(
            query, str(guild_id), str(user_id), guild_name, user_name
        )

        new_user = {
            "guild_id": str(guild_id),
            "user_id": str(user_id),
            "xp": 0,
            "level": 0,
            "voice_xp_earned": 0,
            "guild_name": guild_name,
            "username": user_name,
        }
        self.user_cache[(guild_id, user_id)] = new_user
        return new_user

    async def update_user_xp(
        self, guild_id: int, user_id: int, xp_gain: int, voice_xp_gain: int = 0
    ):
        user = await self.get_user(guild_id, user_id)
        new_xp = user.get("xp", 0) + xp_gain
        new_level = new_xp // 1000
        new_voice_xp = user.get("voice_xp_earned", 0) + voice_xp_gain

        query = "UPDATE public.users SET xp = $3, level = $4, voice_xp_earned = $5 WHERE guild_id = $1 AND user_id = $2"
        await self.pool.execute(
            query, str(guild_id), str(user_id), new_xp, new_level, new_voice_xp
        )

        user.update(xp=new_xp, level=new_level, voice_xp_earned=new_voice_xp)
        self.user_cache[(guild_id, user_id)] = user
        return new_level

    # --- Event Handlers ---

    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Cooldown check
        key = (message.guild.id, message.author.id)
        now = datetime.now()
        if (last_msg := self.message_cooldowns.get(key)) and (
            now - last_msg
        ).total_seconds() < 60:
            return
        self.message_cooldowns[key] = now

        # Fetch dynamic settings
        settings = await self.get_guild_settings(message.guild.id)
        xp_text = settings.get("xp_per_message", 10)
        xp_image = settings.get("xp_per_image", 15)

        amount = (
            xp_image
            if any(
                att.content_type and att.content_type.startswith("image/")
                for att in message.attachments
            )
            else xp_text
        )

        user_data = await self.get_user(message.guild.id, message.author.id)
        old_level = user_data.get("level", 0)
        new_level = await self.update_user_xp(
            message.guild.id, message.author.id, amount
        )

        if new_level > old_level:
            await self._check_and_handle_level_up(message.author, new_level)

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot or not member.guild:
            return

        key = (member.guild.id, member.id)
        now = datetime.now(IST)

        is_active_before = before.channel and not before.afk and not before.self_deaf
        is_active_after = after.channel and not after.afk and not after.self_deaf

        if is_active_before and not is_active_after:
            if start_time := self.voice_sessions.pop(key, None):
                await self._award_voice_xp(member, start_time)
        elif not is_active_before and is_active_after:
            self.voice_sessions[key] = now

    # --- Core Leveling & Role Logic ---

    async def _award_voice_xp(self, member: discord.Member, start_time: datetime):
        settings = await self.get_guild_settings(member.guild.id)
        voice_xp_limit = settings.get("voice_xp_limit", 1500)
        xp_per_minute = settings.get("xp_per_minute_in_voice", 4)

        user = await self.get_user(member.guild.id, member.id)
        if user.get("voice_xp_earned", 0) >= voice_xp_limit:
            return

        elapsed_seconds = (datetime.now(IST) - start_time).total_seconds()
        xp_to_add = int((elapsed_seconds / 60) * xp_per_minute)
        if xp_to_add <= 0:
            return

        remaining_room = voice_xp_limit - user.get("voice_xp_earned", 0)
        xp_to_add = min(xp_to_add, remaining_room)

        if xp_to_add > 0:
            old_level = user.get("level", 0)
            new_level = await self.update_user_xp(
                member.guild.id, member.id, xp_to_add, voice_xp_gain=xp_to_add
            )
            if new_level > old_level:
                await self._check_and_handle_level_up(member, new_level)

    async def _check_and_handle_level_up(self, member: discord.Member, new_level: int):
        last_notified = (
            await self.pool.fetchval(
                "SELECT level FROM public.last_notified_level WHERE guild_id = $1 AND user_id = $2",
                str(member.guild.id),
                str(member.id),
            )
            or 0
        )
        if new_level <= last_notified:
            return

        log.info(
            f"LEVEL UP: {member.name} in '{member.guild.name}' reached Level {new_level}"
        )
        earned_role_id = await self.upgrade_user_roles(member, new_level)
        earned_role = member.guild.get_role(earned_role_id) if earned_role_id else None

        channel_id_str = await self.pool.fetchval(
            "SELECT channel_id FROM public.level_notify_channel WHERE guild_id = $1",
            str(member.guild.id),
        )
        if channel_id_str and (channel := self.bot.get_channel(int(channel_id_str))):
            msg = f"🚀 Congrats {member.mention}! You've reached **Level {new_level}**!"
            if earned_role:
                msg = f"🎉 Congrats {member.mention}! You've reached **Level {new_level}** and earned the **{earned_role.name}** role!"
            try:
                await channel.send(msg)
            except discord.HTTPException as e:
                log.error(
                    f"Failed to send level-up message to channel {channel.id}: {e}"
                )

        query = "INSERT INTO public.last_notified_level (guild_id, user_id, level, guild_name, username) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (guild_id, user_id) DO UPDATE SET level = $3, username = $5"
        await self.pool.execute(
            query,
            str(member.guild.id),
            str(member.id),
            new_level,
            member.guild.name,
            member.name,
        )

    async def upgrade_user_roles(
        self, member: discord.Member, new_level: int
    ) -> int | None:
        roles = await self.pool.fetch(
            "SELECT role_id, level FROM public.level_roles WHERE guild_id = $1 ORDER BY level DESC",
            str(member.guild.id),
        )
        if not roles:
            return None

        target_role_id = next(
            (int(r["role_id"]) for r in roles if new_level >= r["level"]), None
        )
        all_level_role_ids = {int(r["role_id"]) for r in roles}
        current_user_role_ids = {r.id for r in member.roles}

        roles_to_add_ids = (
            {target_role_id} - current_user_role_ids if target_role_id else set()
        )
        roles_to_remove_ids = (current_user_role_ids & all_level_role_ids) - {
            target_role_id
        }

        try:
            if roles_to_add_ids:
                await member.add_roles(
                    *[
                        r
                        for r_id in roles_to_add_ids
                        if (r := member.guild.get_role(r_id))
                    ],
                    reason=f"Reached Level {new_level}",
                )
            if roles_to_remove_ids:
                await member.remove_roles(
                    *[
                        r
                        for r_id in roles_to_remove_ids
                        if (r := member.guild.get_role(r_id))
                    ],
                    reason="Level role sync",
                )
            if roles_to_add_ids or roles_to_remove_ids:
                return target_role_id
        except discord.Forbidden:
            log.error(
                f"Bot lacks permission to manage roles in guild {member.guild.id}"
            )
        return None

    # --- Reset Logic ---

    async def _perform_full_reset(self, guild: discord.Guild):
        log.warning(f"Performing full XP reset for guild: {guild.name} ({guild.id})")
        roles_removed, users_affected = 0, 0

        reward_roles = await self.pool.fetch(
            "SELECT role_id FROM public.level_roles WHERE guild_id = $1", str(guild.id)
        )
        if reward_roles:
            reward_role_ids = {int(r["role_id"]) for r in reward_roles}
            for member in guild.members:
                if member.bot:
                    continue
                roles_to_strip = [r for r in member.roles if r.id in reward_role_ids]
                if roles_to_strip:
                    try:
                        await member.remove_roles(*roles_to_strip, reason="XP Reset")
                        roles_removed += len(roles_to_strip)
                        users_affected += 1
                    except discord.Forbidden:
                        log.warning(
                            f"No permission to remove roles from {member.display_name} in {guild.name}"
                        )

        await self.pool.execute(
            "UPDATE public.users SET xp = 0, level = 0, voice_xp_earned = 0 WHERE guild_id = $1",
            str(guild.id),
        )
        await self.pool.execute(
            "UPDATE public.last_notified_level SET level = 0 WHERE guild_id = $1",
            str(guild.id),
        )

        for key in [k for k in self.user_cache if k[0] == guild.id]:
            del self.user_cache[key]
        return roles_removed, users_affected

    async def check_and_run_auto_reset(self):
        now_utc = datetime.now(timezone.utc)
        configs = await self.pool.fetch("SELECT * FROM public.auto_reset")
        for row in configs:
            if (now_utc - row["last_reset"]).days >= row["days"]:
                if guild := self.bot.get_guild(int(row["guild_id"])):
                    log.info(
                        f"Auto-reset triggered for guild {guild.name} ({guild.id})"
                    )
                    await self._perform_full_reset(guild)
                    await self.pool.execute(
                        "UPDATE public.auto_reset SET last_reset = NOW() WHERE guild_id = $1",
                        str(guild.id),
                    )

    @tasks.loop(hours=1)
    async def reset_loop(self):
        await self.check_and_run_auto_reset()

    @reset_loop.before_loop
    async def before_reset_loop(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def cleanup_cooldowns(self):
        """Remove old cooldown entries to prevent memory leaks."""
        now = datetime.now()
        cutoff = now - timedelta(hours=1)

        old_keys = [
            key
            for key, timestamp in self.message_cooldowns.items()
            if timestamp < cutoff
        ]

        for key in old_keys:
            del self.message_cooldowns[key]

        if old_keys:
            log.info(f"🧹 Cleaned up {len(old_keys)} old cooldown entries")

    # --- Slash Commands ---

    def register_commands(self):

        @self.bot.tree.command(
            name="l1-level", description="Check your or another user's level."
        )
        async def level(
            interaction: discord.Interaction, member: discord.Member = None
        ):
            target = member or interaction.user
            user_data = await self.get_user(interaction.guild.id, target.id)
            settings = await self.get_guild_settings(interaction.guild.id)
            voice_xp_limit = settings.get("voice_xp_limit", 1500)

            embed = discord.Embed(
                title=f"📊 Level Info for {target.display_name}", color=0x3498DB
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            embed.add_field(name="Level", value=user_data.get("level", 0))
            embed.add_field(name="Total XP", value=user_data.get("xp", 0))
            embed.add_field(
                name="Voice XP This Period",
                value=f"{user_data.get('voice_xp_earned', 0)} / {voice_xp_limit}",
                inline=False,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        @self.bot.tree.command(
            name="l2-leaderboard",
            description="Show the top 10 users on the leaderboard.",
        )
        async def leaderboard(interaction: discord.Interaction):
            await interaction.response.defer()
            data = await self.pool.fetch(
                "SELECT * FROM public.users WHERE guild_id = $1 ORDER BY xp DESC LIMIT 10",
                str(interaction.guild.id),
            )
            embed = discord.Embed(
                title=f"🏆 Leaderboard - {interaction.guild.name}", color=0xF1C40F
            )
            if not data:
                embed.description = "No one has earned any XP yet!"
            for i, row in enumerate(data, 1):
                try:
                    user_obj = interaction.guild.get_member(
                        int(row["user_id"])
                    ) or await self.bot.fetch_user(int(row["user_id"]))
                    name = user_obj.display_name
                except discord.NotFound:
                    name = row.get("username", "Unknown User")
                embed.add_field(
                    name=f"#{i} {name}",
                    value=f"Lvl {row['level']} ({row['xp']} XP)",
                    inline=False,
                )
            await interaction.followup.send(embed=embed)

        @self.bot.tree.command(
            name="l3-setup-level-reward",
            description="Set a role reward for reaching a specific level.",
        )
        @app_commands.checks.has_permissions(manage_roles=True)
        async def setup_level_reward(
            interaction: discord.Interaction, level: int, role: discord.Role
        ):
            await interaction.response.defer(ephemeral=True)
            query = "INSERT INTO public.level_roles (guild_id, level, role_id, guild_name, role_name) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (guild_id, level) DO UPDATE SET role_id = $3, role_name = $5"
            await self.pool.execute(
                query,
                str(interaction.guild.id),
                level,
                str(role.id),
                interaction.guild.name,
                role.name,
            )
            await interaction.followup.send(
                f"✅ Reward set: Users reaching Level {level} will now receive the {role.mention} role.",
                ephemeral=True,
            )

        @self.bot.tree.command(
            name="l4-level-reward-show",
            description="Show configured level rewards in this server.",
        )
        @app_commands.checks.has_permissions(view_audit_log=True)
        async def level_reward_show(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            rewards = await self.pool.fetch(
                "SELECT level, role_id, role_name FROM public.level_roles WHERE guild_id = $1 ORDER BY level DESC",
                str(interaction.guild.id),
            )
            if not rewards:
                await interaction.followup.send(
                    "❌ No level rewards are configured for this server.",
                    ephemeral=True,
                )
                return

            description = "Here are the role rewards for reaching specific levels:\n"
            for row in rewards:
                role = interaction.guild.get_role(int(row["role_id"]))
                level_info = f"\n**Level {row['level']}** → "
                if role:
                    description += level_info + role.mention
                else:
                    role_name = row["role_name"]
                    description += level_info + f"`{role_name}` (Deleted)"

            embed = discord.Embed(
                title="🏅 Level Rewards",
                description=description,
                color=discord.Color.gold(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        @self.bot.tree.command(
            name="l5-notify-level-msg",
            description="Set a channel for level-up messages.",
        )
        @app_commands.checks.has_permissions(manage_channels=True)
        async def notify_level_msg(
            interaction: discord.Interaction, channel: discord.TextChannel
        ):
            await interaction.response.defer(ephemeral=True)
            query = "INSERT INTO public.level_notify_channel (guild_id, channel_id, guild_name, channel_name) VALUES ($1, $2, $3, $4) ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2, channel_name = $4"
            await self.pool.execute(
                query,
                str(interaction.guild.id),
                str(channel.id),
                interaction.guild.name,
                channel.name,
            )
            await interaction.followup.send(
                f"✅ Level-up messages will now be sent in {channel.mention}.",
                ephemeral=True,
            )

        @self.bot.tree.command(
            name="l6-set-auto-reset",
            description="Set automatic XP reset schedule (in days).",
        )
        @app_commands.checks.has_permissions(administrator=True)
        async def set_auto_reset(
            interaction: discord.Interaction, days: app_commands.Range[int, 1, 365]
        ):
            await interaction.response.defer(ephemeral=True)
            query = "INSERT INTO public.auto_reset (guild_id, days, last_reset, guild_name) VALUES ($1, $2, NOW(), $3) ON CONFLICT (guild_id) DO UPDATE SET days = $2, last_reset = NOW()"
            await self.pool.execute(
                query, str(interaction.guild.id), days, interaction.guild.name
            )
            next_reset = discord.utils.format_dt(
                datetime.now(timezone.utc) + timedelta(days=days), "F"
            )
            await interaction.followup.send(
                f"♻️ Auto-reset has been set for every **{days}** day(s). The next reset is scheduled for {next_reset}.",
                ephemeral=True,
            )

        @self.bot.tree.command(
            name="l7-show-auto-reset",
            description="Show the current auto-reset configuration.",
        )
        @app_commands.checks.has_permissions(administrator=True)
        async def show_auto_reset(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            config = await self.pool.fetchrow(
                "SELECT * FROM public.auto_reset WHERE guild_id = $1",
                str(interaction.guild.id),
            )
            if not config:
                await interaction.followup.send(
                    "❌ Auto-reset is not configured for this server.", ephemeral=True
                )
                return

            next_reset_time = config["last_reset"] + timedelta(days=config["days"])
            embed = discord.Embed(title="♻️ Auto-Reset Configuration", color=0x3498DB)
            embed.add_field(
                name="Reset Interval", value=f"Every {config['days']} day(s)"
            )
            embed.add_field(
                name="Last Reset",
                value=discord.utils.format_dt(config["last_reset"], "R"),
            )
            embed.add_field(
                name="Next Scheduled Reset",
                value=discord.utils.format_dt(next_reset_time, "F"),
                inline=False,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        @self.bot.tree.command(
            name="l8-stop-auto-reset",
            description="Disable the automatic XP reset for this server.",
        )
        @app_commands.checks.has_permissions(administrator=True)
        async def stop_auto_reset(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            result = await self.pool.execute(
                "DELETE FROM public.auto_reset WHERE guild_id = $1",
                str(interaction.guild.id),
            )
            if result == "DELETE 1":
                await interaction.followup.send(
                    "♻️ Automatic XP reset has been disabled.", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ Auto-reset was not enabled on this server.", ephemeral=True
                )

        @self.bot.tree.command(
            name="l9-reset-xp",
            description="MANUALLY reset all XP and remove reward roles.",
        )
        @app_commands.checks.has_permissions(administrator=True)
        async def reset_xp(interaction: discord.Interaction):
            await interaction.response.defer(thinking=True, ephemeral=False)
            roles_removed, users_affected = await self._perform_full_reset(
                interaction.guild
            )
            await interaction.followup.send(
                f"♻️ **Manual XP Reset Complete!**\n- All user XP and levels have been reset to 0.\n- Removed {roles_removed} reward roles from {users_affected} users."
            )

        @self.bot.tree.command(
            name="l10-upgrade-all-roles",
            description="Manually sync roles for all users based on their current level.",
        )
        @app_commands.checks.has_permissions(manage_roles=True)
        async def upgrade_all_roles(interaction: discord.Interaction):
            await interaction.response.defer(thinking=True, ephemeral=True)
            users_data = await self.pool.fetch(
                "SELECT user_id, level FROM public.users WHERE guild_id = $1",
                str(interaction.guild.id),
            )
            if not users_data:
                await interaction.followup.send(
                    "No users found in the database for this server."
                )
                return

            changed_count = 0
            for user in users_data:
                member = interaction.guild.get_member(int(user["user_id"]))
                if member:
                    if await self.upgrade_user_roles(member, user["level"]):
                        changed_count += 1

            await interaction.followup.send(
                f"🔄 Role synchronization complete! Updated roles for {changed_count} member(s).",
                ephemeral=True,
            )

        log.info("💻 Leveling commands registered.")
