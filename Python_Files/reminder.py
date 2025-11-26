import discord
from discord.ext import commands, tasks
import asyncpg
import logging
from datetime import datetime, timedelta
import pytz
import re
import secrets

log = logging.getLogger(__name__)


class ReminderManager:
    """Manages reminders with timezone support, intervals, and patterns"""

    def __init__(self, bot, pool):
        self.bot = bot
        self.pool = pool
        self.default_timezone = "Asia/Kolkata"  # IST

    async def start(self):
        """Initialize the reminder system"""
        log.info("🔔 Reminder Manager initialized")
        self.check_reminders_task.start()

    def register_commands(self):
        """Register all reminder slash commands"""

        @self.bot.tree.command(
            name="r0-list",
            description="List all active reminders in this server"
        )
        async def list_reminders(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)

            reminders = await self.pool.fetch(
                """
                SELECT * FROM public.reminders 
                WHERE guild_id = $1 AND status IN ('active', 'paused')
                ORDER BY next_run ASC
                """,
                str(interaction.guild.id),
            )

            if not reminders:
                await interaction.followup.send(
                    "📭 No active reminders found.", ephemeral=True
                )
                return

            embed = discord.Embed(
                title="🔔 Active Reminders",
                description=f"Found {len(reminders)} reminder(s)",
                color=discord.Color.blue(),
            )

            for reminder in reminders[:10]:  # Show first 10
                channel = self.bot.get_channel(int(reminder["channel_id"]))
                role_text = (
                    f"<@&{reminder['role_id']}>" if reminder["role_id"] else "None"
                )

                status_emoji = "⏸️" if reminder["status"] == "paused" else "✅"

                value = f"**Status:** {status_emoji} {reminder['status'].title()}\n"
                value += f"**Channel:** {channel.mention if channel else 'Deleted'}\n"
                value += f"**Role:** {role_text}\n"
                value += f"**Next Run:** {discord.utils.format_dt(reminder['next_run'], 'R')}\n"
                value += f"**Interval:** {reminder['interval']}\n"
                value += f"**Timezone:** {reminder['timezone']}\n"
                value += f"**Message:** {reminder['message'][:50]}..."

                embed.add_field(
                    name=f"ID: {reminder['reminder_id']}", value=value, inline=False
                )

            if len(reminders) > 10:
                embed.set_footer(text=f"Showing 10 of {len(reminders)} reminders")

            await interaction.followup.send(embed=embed, ephemeral=True)

        @self.bot.tree.command(
            name="r1-create",
            description="Create a new reminder with advanced options"
        )
        @discord.app_commands.describe(
            channel="Channel where reminder will be sent",
            message="Reminder message content",
            time="Time (HH:mm or MM/DD HH:mm)",
            interval="Repeat interval (1d, 2d, 6h, 30m, etc.) or 'once'",
            role="Role to ping (optional)",
            timezone="Timezone: Asia/Kolkata (IST), America/New_York, Europe/London, UTC (default: IST)",
            pattern="Custom pattern like 1-1-0 (optional - advanced)",
        )
        async def create_reminder(
            interaction: discord.Interaction,
            channel: discord.TextChannel,
            message: str,
            time: str,
            interval: str = "once",
            role: discord.Role = None,
            timezone: str = None,
            pattern: str = None,
        ):
            await interaction.response.defer(ephemeral=True)
            tz = timezone or self.default_timezone
            valid_timezones = {
                "Asia/Kolkata": "🇮🇳 India Standard Time (IST)",
                "America/New_York": "🇺🇸 US Eastern Time",
                "America/Los_Angeles": "🇺🇸 US Pacific Time",
                "Europe/London": "🇬🇧 UK Time",
                "Europe/Paris": "🇫🇷 Central European Time",
                "Asia/Tokyo": "🇯🇵 Japan Time",
                "Asia/Dubai": "🇦🇪 UAE Time",
                "Australia/Sydney": "🇦🇺 Australian Eastern Time",
                "UTC": "🌍 Universal Time",
            }

            try:
                pytz.timezone(tz)
            except:
                tz_list = "\n".join([f"• `{k}` - {v}" for k, v in valid_timezones.items()])
                
                await interaction.followup.send(
                    f"❌ Invalid timezone: `{tz}`\n\n"
                    f"**📍 Common Timezones:**\n{tz_list}\n\n"
                    f"💡 **Tip:** If you don't specify a timezone, it defaults to `Asia/Kolkata` (IST)\n\n"
                    f"🔍 For more timezones, visit: <https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>",
                    ephemeral=True
                )
                return

            parsed_time = self._parse_time(time, tz)
            if not parsed_time:
                await interaction.followup.send(
                    "❌ Invalid time format.\n\n"
                    "**Valid formats:**\n"
                    "• `14:30` - Today at 2:30 PM (or tomorrow if time passed)\n"
                    "• `12/25 09:00` - December 25 at 9:00 AM\n"
                    "• `01/15 18:45` - January 15 at 6:45 PM",
                    ephemeral=True
                )
                return

            if not self._validate_interval(interval):
                await interaction.followup.send(
                    "❌ Invalid interval format.\n\n"
                    "**Valid intervals:**\n"
                    "• `once` - One-time reminder\n"
                    "• `5m` - Every 5 minutes\n"
                    "• `30m` - Every 30 minutes\n"
                    "• `1h` - Every hour\n"
                    "• `6h` - Every 6 hours\n"
                    "• `1d` - Daily\n"
                    "• `2d` - Every 2 days\n"
                    "• `7d` - Weekly",
                    ephemeral=True,
                )
                return

            reminder_id = f"R-{secrets.randbelow(9000) + 1000}"

            try:
                await self.pool.execute(
                    """
                    INSERT INTO public.reminders 
                    (reminder_id, guild_id, channel_id, role_id, message, 
                     start_time, next_run, interval, pattern, timezone, created_by, status)
                    VALUES ($1, $2, $3, $4, $5, $6, $6, $7, $8, $9, $10, 'active')
                    """,
                    reminder_id,
                    str(interaction.guild.id),
                    str(channel.id),
                    str(role.id) if role else None,
                    message,
                    parsed_time,
                    interval,
                    pattern,
                    tz,
                    str(interaction.user.id),
                )

                embed = discord.Embed(
                    title="✅ Reminder Created",
                    description=f"**ID:** `{reminder_id}`",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Channel", value=channel.mention)
                embed.add_field(name="Role", value=role.mention if role else "@here")
                embed.add_field(
                    name="Next Run",
                    value=discord.utils.format_dt(parsed_time, "F"),
                    inline=False,
                )
                embed.add_field(name="Interval", value=interval)
                embed.add_field(name="Timezone", value=f"`{tz}`")
                embed.add_field(name="Message", value=message[:100], inline=False)

                await interaction.followup.send(embed=embed, ephemeral=True)
                log.info(
                    f"✅ Reminder {reminder_id} created by {interaction.user} in {interaction.guild.name}"
                )

            except Exception as e:
                log.error(f"Error creating reminder: {e}")
                await interaction.followup.send(
                    f"❌ Error creating reminder: {str(e)}", ephemeral=True
                )

        @self.bot.tree.command(
            name="r2-delete",
            description="Delete a reminder by ID"
        )
        @discord.app_commands.describe(reminder_id="Reminder ID (e.g., R-1023)")
        async def delete_reminder(interaction: discord.Interaction, reminder_id: str):
            await interaction.response.defer(ephemeral=True)

            result = await self.pool.execute(
                """
                UPDATE public.reminders 
                SET status = 'deleted' 
                WHERE reminder_id = $1 AND guild_id = $2
                """,
                reminder_id,
                str(interaction.guild.id),
            )

            if result == "UPDATE 0":
                await interaction.followup.send(
                    f"❌ Reminder `{reminder_id}` not found.", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"✅ Reminder `{reminder_id}` deleted.", ephemeral=True
                )
                log.info(f"🗑️ Reminder {reminder_id} deleted by {interaction.user}")

        @self.bot.tree.command(
            name="r3-edit",
            description="Edit an existing reminder"
        )
        @discord.app_commands.describe(
            reminder_id="Reminder ID to edit",
            channel="New channel (optional)",
            role="New role (optional)",
            message="New message (optional)",
            time="New time (optional)",
            interval="New interval (optional)",
        )
        async def edit_reminder(
            interaction: discord.Interaction,
            reminder_id: str,
            channel: discord.TextChannel = None,
            role: discord.Role = None,
            message: str = None,
            time: str = None,
            interval: str = None,
        ):
            await interaction.response.defer(ephemeral=True)

            updates = []
            values = []
            idx = 1

            if channel:
                updates.append(f"channel_id = ${idx}")
                values.append(str(channel.id))
                idx += 1

            if role:
                updates.append(f"role_id = ${idx}")
                values.append(str(role.id))
                idx += 1

            if message:
                updates.append(f"message = ${idx}")
                values.append(message)
                idx += 1

            if time:
                parsed = self._parse_time(time, self.default_timezone)
                if parsed:
                    updates.append(f"next_run = ${idx}")
                    values.append(parsed)
                    idx += 1

            if interval:
                if self._validate_interval(interval):
                    updates.append(f"interval = ${idx}")
                    values.append(interval)
                    idx += 1
                else:
                    await interaction.followup.send(
                        "❌ Invalid interval format.", ephemeral=True
                    )
                    return

            if not updates:
                await interaction.followup.send(
                    "❌ No changes provided.", ephemeral=True
                )
                return

            values.append(reminder_id)
            values.append(str(interaction.guild.id))

            query = f"""
                UPDATE public.reminders 
                SET {', '.join(updates)}, updated_at = NOW()
                WHERE reminder_id = ${idx} AND guild_id = ${idx + 1}
            """

            result = await self.pool.execute(query, *values)

            if result == "UPDATE 0":
                await interaction.followup.send(
                    f"❌ Reminder `{reminder_id}` not found.", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"✅ Reminder `{reminder_id}` updated successfully.", ephemeral=True
                )

        @self.bot.tree.command(
            name="r4-pause",
            description="Pause or resume a reminder"
        )
        @discord.app_commands.describe(reminder_id="Reminder ID (e.g., R-1023)")
        async def pause_reminder(interaction: discord.Interaction, reminder_id: str):
            await interaction.response.defer(ephemeral=True)

            current = await self.pool.fetchrow(
                "SELECT status FROM public.reminders WHERE reminder_id = $1 AND guild_id = $2",
                reminder_id,
                str(interaction.guild.id),
            )

            if not current:
                await interaction.followup.send(
                    f"❌ Reminder `{reminder_id}` not found.", ephemeral=True
                )
                return

            new_status = "paused" if current["status"] == "active" else "active"

            await self.pool.execute(
                """
                UPDATE public.reminders 
                SET status = $1, updated_at = NOW()
                WHERE reminder_id = $2 AND guild_id = $3
                """,
                new_status,
                reminder_id,
                str(interaction.guild.id),
            )

            action = "⏸️ paused" if new_status == "paused" else "▶️ resumed"
            await interaction.followup.send(
                f"✅ Reminder `{reminder_id}` {action}.", ephemeral=True
            )
            log.info(f"⏸️ Reminder {reminder_id} {action} by {interaction.user}")

        log.info("✅ Reminder commands registered (r0-list, r1-create, r2-delete, r3-edit, r4-pause)")

    @tasks.loop(minutes=1)
    async def check_reminders_task(self):
        """Check and send due reminders every minute"""
        now = datetime.now(pytz.UTC)

        try:
            due_reminders = await self.pool.fetch(
                """
                SELECT * FROM public.reminders 
                WHERE status = 'active' 
                AND next_run <= $1
                """,
                now,
            )

            for reminder in due_reminders:
                await self._send_reminder(reminder)

        except Exception as e:
            log.error(f"Error checking reminders: {e}")

    async def _send_reminder(self, reminder):
        """Send a reminder and schedule next run"""
        try:
            guild = self.bot.get_guild(int(reminder["guild_id"]))
            if not guild:
                return

            channel = guild.get_channel(int(reminder["channel_id"]))
            if not channel:
                log.warning(
                    f"Channel {reminder['channel_id']} not found for reminder {reminder['reminder_id']}"
                )
                return

            content = ""
            if reminder["role_id"]:
                content = f"<@&{reminder['role_id']}>\n"
            content += reminder["message"]

            await channel.send(content)

            next_run = self._calculate_next_run(reminder)

            if next_run:
                await self.pool.execute(
                    """
                    UPDATE public.reminders 
                    SET next_run = $1, last_run = NOW(), run_count = run_count + 1
                    WHERE reminder_id = $2
                    """,
                    next_run,
                    reminder["reminder_id"],
                )
            else:
                await self.pool.execute(
                    """
                    UPDATE public.reminders 
                    SET status = 'completed', last_run = NOW(), run_count = run_count + 1
                    WHERE reminder_id = $1
                    """,
                    reminder["reminder_id"],
                )

            log.info(f"✅ Reminder {reminder['reminder_id']} sent successfully")

        except Exception as e:
            log.error(f"Error sending reminder {reminder['reminder_id']}: {e}")

    def _parse_time(self, time_str: str, timezone: str):
        """Parse time string into datetime"""
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)

        try:
            # HH:mm format
            if ":" in time_str and "/" not in time_str:
                hour, minute = map(int, time_str.split(":"))
                dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

                if dt <= now:
                    dt += timedelta(days=1)

                return dt.astimezone(pytz.UTC)

            # MM/DD HH:mm format
            elif "/" in time_str:
                date_part, time_part = time_str.split()
                month, day = map(int, date_part.split("/"))
                hour, minute = map(int, time_part.split(":"))

                dt = now.replace(
                    month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0
                )
                return dt.astimezone(pytz.UTC)

        except:
            return None

    def _validate_interval(self, interval: str) -> bool:
        """Validate interval format"""
        if interval == "once":
            return True

        # Pattern: 1d, 2d, 6h, 30m
        pattern = r"^\d+[dhm]$"
        return bool(re.match(pattern, interval))

    def _calculate_next_run(self, reminder):
        """Calculate next run time based on interval"""
        interval = reminder["interval"]

        if interval == "once":
            return None

        last_run = reminder["next_run"]

        match = re.match(r"^(\d+)([dhm])$", interval)
        if not match:
            return None

        amount, unit = match.groups()
        amount = int(amount)

        if unit == "m":
            next_run = last_run + timedelta(minutes=amount)
        elif unit == "h":
            next_run = last_run + timedelta(hours=amount)
        elif unit == "d":
            next_run = last_run + timedelta(days=amount)

        return next_run

    @check_reminders_task.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()
        log.info("⏰ Starting reminder check task...")