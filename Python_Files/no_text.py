# Python_Files/no_text.py

import discord
from discord import app_commands
from discord.ext import commands
import re
import asyncio
import asyncpg
import logging

log = logging.getLogger(__name__)


class NoTextManager:
    def __init__(self, bot: commands.Bot, pool: asyncpg.Pool):
        self.bot = bot
        self.pool = pool
        # Regex to find any URL
        self.url_pattern = re.compile(
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
        )
        # Regex to specifically find Discord invite links
        self.discord_link_pattern = re.compile(
            r"(?:https?://)?(?:www\.)?discord(?:app\.com/invite|\.gg)/[a-zA-Z0-9]+"
        )
        # Regex to detect image URLs (jpg/png/gif/webp)
        self.image_url_pattern = re.compile(
            r"https?://\S+\.(?:png|jpe?g|gif|webp)(?:\?\S*)?$", re.IGNORECASE
        )
        log.info("No-Text system has been initialized.")

    async def start(self):
        """Starts the manager by adding its event listener."""
        self.bot.add_listener(self.on_message, "on_message")

    async def is_bypass(self, member: discord.Member) -> bool:
        """Checks if a member has a role that bypasses restrictions."""
        # Server owners and admins always bypass
        if member.guild_permissions.administrator:
            return True

        async with self.pool.acquire() as conn:
            bypass_roles = await conn.fetch(
                "SELECT role_id FROM public.bypass_roles WHERE guild_id = $1",
                str(member.guild.id),
            )

        if not bypass_roles:
            return False

        bypass_role_ids = {int(r["role_id"]) for r in bypass_roles}
        member_role_ids = {r.id for r in member.roles}

        return not bypass_role_ids.isdisjoint(member_role_ids)

    async def on_message(self, message: discord.Message):
        """The core message handler that enforces all channel restrictions."""
        if (
            message.author.bot
            or not message.guild
            or await self.is_bypass(message.author)
        ):
            return

        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)

        async with self.pool.acquire() as conn:
            is_no_links = await conn.fetchval(
                "SELECT 1 FROM public.no_links_channels WHERE guild_id = $1 AND channel_id = $2",
                guild_id,
                channel_id,
            )
            is_no_discord_links = await conn.fetchval(
                "SELECT 1 FROM public.no_discord_links_channels WHERE guild_id = $1 AND channel_id = $2",
                guild_id,
                channel_id,
            )
            no_text_config = await conn.fetchrow(
                "SELECT redirect_channel_id FROM public.no_text_channels WHERE guild_id = $1 AND channel_id = $2",
                guild_id,
                channel_id,
            )
            # New: fetch text-only config (disallow attachments/embeds/image links)
            text_only_config = await conn.fetchrow(
                "SELECT redirect_channel_id FROM public.text_only_channels WHERE guild_id = $1 AND channel_id = $2",
                guild_id,
                channel_id,
            )

        try:
            # 1. Check for "No Links" (most restrictive)
            if is_no_links and self.url_pattern.search(message.content):
                await message.delete()
                return

            # 2. Check for "No Discord Links"
            if is_no_discord_links and self.discord_link_pattern.search(
                message.content
            ):
                await message.delete()
                return

            # 3. Check for "Media-Only" (No Text)
            is_media = (
                message.attachments
                or self.url_pattern.search(message.content)
                or message.embeds
            )
            if no_text_config and not is_media:
                await message.delete()
                redirect_channel = self.bot.get_channel(
                    int(no_text_config["redirect_channel_id"])
                )
                if redirect_channel:
                    warn_msg = await message.channel.send(
                        f"🚫 {message.author.mention}, please use {redirect_channel.mention} for text. This channel is for media only."
                    )
                    await asyncio.sleep(15)
                    await warn_msg.delete()
                return

            # 4. NEW: Check for "Text-Only" (No Attachments/Embeds/Image Links)
            has_restricted_content = (
                message.attachments  # Has file attachments
                or message.embeds  # Has embeds
                or self.image_url_pattern.search(message.content)  # Has image links
            )
            if text_only_config and has_restricted_content:
                await message.delete()
                redirect_channel = self.bot.get_channel(
                    int(text_only_config["redirect_channel_id"])
                )
                if redirect_channel:
                    warn_msg = await message.channel.send(
                        f"🚫 {message.author.mention}, please use {redirect_channel.mention} for media. This channel is for text only."
                    )
                    await asyncio.sleep(15)
                    await warn_msg.delete()
                return

        except discord.Forbidden:
            log.warning(
                f"Missing permissions to delete message in channel {channel_id} (Guild: {guild_id})."
            )
        except discord.NotFound:
            pass
        except Exception as e:
            log.error(f"Error in NoTextManager on_message handler: {e}")

    def register_commands(self):
        """Registers all slash commands for this manager."""

        @self.bot.tree.command(
            name="n1-setup-no-text",
            description="Configure a channel to only allow media and links.",
        )
        @app_commands.checks.has_permissions(manage_channels=True)
        async def setup_no_text(
            interaction: discord.Interaction,
            channel: discord.TextChannel,
            redirect_channel: discord.TextChannel,
        ):
            await interaction.response.defer(ephemeral=True)
            query = "INSERT INTO public.no_text_channels (guild_id, channel_id, guild_name, channel_name, redirect_channel_id) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (guild_id, channel_id) DO UPDATE SET redirect_channel_id = $5"
            await self.pool.execute(
                query,
                str(interaction.guild.id),
                str(channel.id),
                interaction.guild.name,
                channel.name,
                str(redirect_channel.id),
            )
            await interaction.followup.send(
                f"✅ Media-only rule has been set for {channel.mention}. Text-only messages will be redirected to {redirect_channel.mention}.",
                ephemeral=True,
            )

        @self.bot.tree.command(
            name="n2-remove-no-text",
            description="Remove the media-only restriction from a channel.",
        )
        @app_commands.checks.has_permissions(manage_channels=True)
        async def remove_no_text(
            interaction: discord.Interaction, channel: discord.TextChannel
        ):
            await interaction.response.defer(ephemeral=True)
            result = await self.pool.execute(
                "DELETE FROM public.no_text_channels WHERE guild_id = $1 AND channel_id = $2",
                str(interaction.guild.id),
                str(channel.id),
            )
            if result == "DELETE 1":
                await interaction.followup.send(
                    f"✅ The media-only restriction has been removed from {channel.mention}.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"❌ {channel.mention} was not configured as a media-only channel.",
                    ephemeral=True,
                )

        @self.bot.tree.command(
            name="n3-bypass-no-text",
            description="Allow a role to bypass all message restrictions.",
        )
        @app_commands.checks.has_permissions(manage_roles=True)
        async def bypass_no_text(interaction: discord.Interaction, role: discord.Role):
            await interaction.response.defer(ephemeral=True)
            query = "INSERT INTO public.bypass_roles (guild_id, role_id, guild_name, role_name) VALUES ($1, $2, $3, $4) ON CONFLICT (guild_id, role_id) DO NOTHING"
            await self.pool.execute(
                query,
                str(interaction.guild.id),
                str(role.id),
                interaction.guild.name,
                role.name,
            )
            await interaction.followup.send(
                f"✅ {role.mention} can now bypass all channel restrictions.",
                ephemeral=True,
            )

        @self.bot.tree.command(
            name="n4-show-bypass-roles",
            description="Show all roles that can bypass restrictions.",
        )
        @app_commands.checks.has_permissions(manage_roles=True)
        async def show_bypass_roles(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            roles = await self.pool.fetch(
                "SELECT role_id, role_name FROM public.bypass_roles WHERE guild_id = $1",
                str(interaction.guild.id),
            )
            if not roles:
                await interaction.followup.send(
                    "❌ No bypass roles are configured for this server.", ephemeral=True
                )
                return

            description = (
                "Users with these roles can ignore all channel message restrictions:\n"
            )
            for record in roles:
                role = interaction.guild.get_role(int(record["role_id"]))
                if role:
                    description += f"\n• {role.mention}"
                else:
                    role_name = record["role_name"]
                    description += f"\n• `{role_name}` (Deleted Role)"

            embed = discord.Embed(
                title="🛡️ Bypass Roles",
                description=description,
                color=discord.Color.gold(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        @self.bot.tree.command(
            name="n5-remove-bypass-role", description="Remove a role's bypass ability."
        )
        @app_commands.checks.has_permissions(manage_roles=True)
        async def remove_bypass_role(
            interaction: discord.Interaction, role: discord.Role
        ):
            await interaction.response.defer(ephemeral=True)
            result = await self.pool.execute(
                "DELETE FROM public.bypass_roles WHERE guild_id = $1 AND role_id = $2",
                str(interaction.guild.id),
                str(role.id),
            )
            if result == "DELETE 1":
                await interaction.followup.send(
                    f"✅ {role.mention} can no longer bypass channel restrictions.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"❌ {role.mention} was not configured as a bypass role.",
                    ephemeral=True,
                )

        @self.bot.tree.command(
            name="n6-no-discord-link",
            description="Silently delete Discord invite links in a channel.",
        )
        @app_commands.checks.has_permissions(manage_channels=True)
        async def no_discord_link(
            interaction: discord.Interaction, channel: discord.TextChannel
        ):
            await interaction.response.defer(ephemeral=True)
            query = "INSERT INTO public.no_discord_links_channels (guild_id, channel_id, guild_name, channel_name) VALUES ($1, $2, $3, $4) ON CONFLICT (guild_id, channel_id) DO NOTHING"
            await self.pool.execute(
                query,
                str(interaction.guild.id),
                str(channel.id),
                interaction.guild.name,
                channel.name,
            )
            await interaction.followup.send(
                f"✅ Discord invite links will now be deleted in {channel.mention}.",
                ephemeral=True,
            )

        @self.bot.tree.command(
            name="n7-no-links", description="Silently delete ALL links in a channel."
        )
        @app_commands.checks.has_permissions(manage_channels=True)
        async def no_links(
            interaction: discord.Interaction, channel: discord.TextChannel
        ):
            await interaction.response.defer(ephemeral=True)
            query = "INSERT INTO public.no_links_channels (guild_id, channel_id, guild_name, channel_name) VALUES ($1, $2, $3, $4) ON CONFLICT (guild_id, channel_id) DO NOTHING"
            await self.pool.execute(
                query,
                str(interaction.guild.id),
                str(channel.id),
                interaction.guild.name,
                channel.name,
            )
            await interaction.followup.send(
                f"✅ All links will now be deleted in {channel.mention}.",
                ephemeral=True,
            )

        @self.bot.tree.command(
            name="n8-remove-no-discord-link",
            description="Stop deleting Discord invite links in a channel.",
        )
        @app_commands.checks.has_permissions(manage_channels=True)
        async def remove_no_discord_link(
            interaction: discord.Interaction, channel: discord.TextChannel
        ):
            await interaction.response.defer(ephemeral=True)
            result = await self.pool.execute(
                "DELETE FROM public.no_discord_links_channels WHERE guild_id = $1 AND channel_id = $2",
                str(interaction.guild.id),
                str(channel.id),
            )
            if result == "DELETE 1":
                await interaction.followup.send(
                    f"✅ Removed the no-discord-link rule from {channel.mention}.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"❌ {channel.mention} was not configured to block Discord links.",
                    ephemeral=True,
                )

        @self.bot.tree.command(
            name="n9-remove-no-links",
            description="Stop deleting all links in a channel.",
        )
        @app_commands.checks.has_permissions(manage_channels=True)
        async def remove_no_links(
            interaction: discord.Interaction, channel: discord.TextChannel
        ):
            await interaction.response.defer(ephemeral=True)
            result = await self.pool.execute(
                "DELETE FROM public.no_links_channels WHERE guild_id = $1 AND channel_id = $2",
                str(interaction.guild.id),
                str(channel.id),
            )
            if result == "DELETE 1":
                await interaction.followup.send(
                    f"✅ Removed the no-links rule from {channel.mention}.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"❌ {channel.mention} was not configured to block all links.",
                    ephemeral=True,
                )

        # NEW COMMANDS FOR TEXT-ONLY FEATURE

        @self.bot.tree.command(
            name="n10-setup-text-only",
            description="Configure a channel to only allow plain text (no images, attachments, embeds).",
        )
        @app_commands.checks.has_permissions(manage_channels=True)
        async def setup_text_only(
            interaction: discord.Interaction,
            channel: discord.TextChannel,
            redirect_channel: discord.TextChannel,
        ):
            await interaction.response.defer(ephemeral=True)
            query = "INSERT INTO public.text_only_channels (guild_id, channel_id, guild_name, channel_name, redirect_channel_id) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (guild_id, channel_id) DO UPDATE SET redirect_channel_id = $5"
            await self.pool.execute(
                query,
                str(interaction.guild.id),
                str(channel.id),
                interaction.guild.name,
                channel.name,
                str(redirect_channel.id),
            )
            await interaction.followup.send(
                f"✅ Text-only rule has been set for {channel.mention}. Media will be redirected to {redirect_channel.mention}.",
                ephemeral=True,
            )

        @self.bot.tree.command(
            name="n11-remove-text-only",
            description="Remove the text-only restriction from a channel.",
        )
        @app_commands.checks.has_permissions(manage_channels=True)
        async def remove_text_only(
            interaction: discord.Interaction, channel: discord.TextChannel
        ):
            await interaction.response.defer(ephemeral=True)
            result = await self.pool.execute(
                "DELETE FROM public.text_only_channels WHERE guild_id = $1 AND channel_id = $2",
                str(interaction.guild.id),
                str(channel.id),
            )
            if result == "DELETE 1":
                await interaction.followup.send(
                    f"✅ The text-only restriction has been removed from {channel.mention}.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"❌ {channel.mention} was not configured as a text-only channel.",
                    ephemeral=True,
                )

        log.info("💻 No-Text commands registered.")
