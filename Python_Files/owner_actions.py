# Python_Files/owner_actions.py

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
import asyncpg
import logging

log = logging.getLogger(__name__)

class OwnerActionsManager:
    """Manages owner-exclusive actions like leaving or banning guilds."""

    def __init__(self, bot: commands.Bot, pool: asyncpg.Pool):
        self.bot = bot
        self.pool = pool
        log.info("Owner Actions system has been initialized.")

    async def is_guild_banned(self, guild_id: int) -> bool:
        """Checks if a guild ID is in the banned_guilds table."""
        try:
            query = "SELECT 1 FROM public.banned_guilds WHERE guild_id = $1"
            # fetchval returns the value of the first column of the first row, or None.
            is_banned = await self.pool.fetchval(query, str(guild_id))
            return is_banned is not None
        except Exception as e:
            log.error(f"Error checking if guild {guild_id} is banned: {e}")
            return False  # Fail safe: if DB check fails, don't assume it's banned.

    def register_commands(self):
        """Registers all owner-only slash commands."""

        # A custom check to ensure only the bot owner can use these commands
        async def is_bot_owner(interaction: discord.Interaction) -> bool:
            return await self.bot.is_owner(interaction.user)

        @self.bot.tree.command(
            name="g3-serverlist",
            description="Lists all servers the bot is in (Bot Owner only).",
        )
        @app_commands.check(is_bot_owner)
        async def serverlist(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)

            description = ""
            for guild in sorted(self.bot.guilds, key=lambda g: g.name):
                description += f"- **{guild.name}** (ID: `{guild.id}`)\n"

            embed = discord.Embed(
                title=f"🔎 Bot is in {len(self.bot.guilds)} Servers",
                description=description,
                color=discord.Color.blurple(),
            )
            await interaction.followup.send(embed=embed)

        @self.bot.tree.command(
            name="g4-leaveserver",
            description="Forces the bot to leave a specific server (Bot Owner only).",
        )
        @app_commands.check(is_bot_owner)
        @app_commands.describe(guild_id="The ID of the server to leave.")
        async def leaveserver(interaction: discord.Interaction, guild_id: str):
            await interaction.response.defer(ephemeral=True)
            try:
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    await interaction.followup.send(
                        f"❌ I am not a member of a server with the ID `{guild_id}`."
                    )
                    return

                await guild.leave()
                log.info(f"Owner forced bot to leave server: {guild.name} ({guild.id})")
                await interaction.followup.send(
                    f"✅ Successfully left the server: **{guild.name}** (`{guild.id}`)."
                )
            except ValueError:
                await interaction.followup.send(
                    "❌ Invalid Guild ID format. Please provide a numeric ID."
                )
            except Exception as e:
                log.error(f"Error during /leaveserver command: {e}")
                await interaction.followup.send(
                    "❌ An unexpected error occurred while trying to leave the server."
                )

        @self.bot.tree.command(
            name="g5-banguild",
            description="Bans a server and forces the bot to leave (Bot Owner only).",
        )
        @app_commands.check(is_bot_owner)
        @app_commands.describe(guild_id="The ID of the server to ban.")
        async def banguild(interaction: discord.Interaction, guild_id: str):
            await interaction.response.defer(ephemeral=True)
            try:
                # Use an UPSERT query to add/update the ban record
                query = """
                    INSERT INTO public.banned_guilds (guild_id, banned_at, banned_by)
                    VALUES ($1, NOW(), $2)
                    ON CONFLICT (guild_id) DO UPDATE SET
                      banned_at = NOW(),
                      banned_by = $2;
                """
                await self.pool.execute(query, guild_id, str(interaction.user.id))

                # If the bot is currently in the server, leave it.
                guild = self.bot.get_guild(int(guild_id))
                if guild:
                    await guild.leave()
                    log.warning(
                        f"Owner BANNED and left server: {guild.name} ({guild.id})"
                    )
                    await interaction.followup.send(
                        f"✅ Server **{guild.name}** (`{guild_id}`) has been banned and I have left."
                    )
                else:
                    log.warning(
                        f"Owner BANNED server ID: {guild_id} (not currently a member)"
                    )
                    await interaction.followup.send(
                        f"✅ Server ID `{guild_id}` has been added to the ban list. I was not a member of it."
                    )
            except ValueError:
                await interaction.followup.send(
                    "❌ Invalid Guild ID format. Please provide a numeric ID."
                )
            except Exception as e:
                log.error(f"Error during /banguild command: {e}")
                await interaction.followup.send(
                    "❌ An unexpected error occurred while banning the server."
                )

        @self.bot.tree.command(
            name="g6-unbanguild",
            description="Removes a server from the ban list (Bot Owner only).",
        )
        @app_commands.check(is_bot_owner)
        @app_commands.describe(guild_id="The ID of the server to unban.")
        async def unbanguild(interaction: discord.Interaction, guild_id: str):
            await interaction.response.defer(ephemeral=True)
            try:
                # The execute function returns a status string like 'DELETE 1' on success
                result = await self.pool.execute(
                    "DELETE FROM public.banned_guilds WHERE guild_id = $1", guild_id
                )

                if result == "DELETE 1":
                    log.info(f"Owner UNBANNED server ID: {guild_id}")
                    await interaction.followup.send(
                        f"✅ Server ID `{guild_id}` has been unbanned."
                    )
                else:
                    await interaction.followup.send(
                        f"❌ Server ID `{guild_id}` was not found in the ban list."
                    )
            except Exception as e:
                log.error(f"Error during /unbanguild command: {e}")
                await interaction.followup.send("❌ An unexpected error occurred.")

        log.info("💻 Owner Action commands registered.")
