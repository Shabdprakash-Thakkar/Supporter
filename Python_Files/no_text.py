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
    """
    Manages granular channel content restrictions using bitwise flags.
    Supports complex combinations like "allow text + links, block Discord invites + images"
    """
    
    # Content type flags (bitwise)
    CONTENT_TYPES = {
        'PLAIN_TEXT': 1,           # 0b00000001
        'DISCORD_INVITES': 2,      # 0b00000010
        'IMAGE_LINKS': 4,          # 0b00000100
        'REGULAR_LINKS': 8,        # 0b00001000
        'IMAGE_ATTACHMENTS': 16,   # 0b00010000
        'FILE_ATTACHMENTS': 32,    # 0b00100000
        'EMBEDS': 64,              # 0b01000000
    }
    
    def __init__(self, bot: commands.Bot, pool: asyncpg.Pool):
        self.bot = bot
        self.pool = pool
        
        # Regex patterns for content detection
        self.url_pattern = re.compile(
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
        )
        self.discord_link_pattern = re.compile(
            r"(?:https?://)?(?:www\.)?discord(?:app\.com/invite|\.gg)/[a-zA-Z0-9]+"
        )
        self.image_url_pattern = re.compile(
            r"https?://\S+\.(?:png|jpe?g|gif|webp)(?:\?\S*)?$", re.IGNORECASE
        )
        
        log.info("✅ No-Text system initialized with granular content filtering")

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

    def detect_content_types(self, message: discord.Message) -> int:
        """
        Detect all content types present in a message and return as bitwise flags.
        
        Returns:
            int: Bitwise OR of all detected content type flags
        """
        detected = 0
        
        # 1. Check for plain text (non-empty content without URLs)
        if message.content.strip():
            # Has text if there's content beyond just URLs
            content_without_urls = self.url_pattern.sub('', message.content).strip()
            if content_without_urls:
                detected |= self.CONTENT_TYPES['PLAIN_TEXT']
        
        # 2. Check for Discord invites
        if self.discord_link_pattern.search(message.content):
            detected |= self.CONTENT_TYPES['DISCORD_INVITES']
        
        # 3. Check for image links
        if self.image_url_pattern.search(message.content):
            detected |= self.CONTENT_TYPES['IMAGE_LINKS']
        
        # 4. Check for regular links (excluding Discord invites and image links)
        all_urls = self.url_pattern.findall(message.content)
        for url in all_urls:
            # Skip if it's a Discord invite or image link
            if not self.discord_link_pattern.match(url) and not self.image_url_pattern.match(url):
                detected |= self.CONTENT_TYPES['REGULAR_LINKS']
                break
        
        # 5. Check for image attachments
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                detected |= self.CONTENT_TYPES['IMAGE_ATTACHMENTS']
                break
        
        # 6. Check for file attachments (non-images)
        for attachment in message.attachments:
            if not attachment.content_type or not attachment.content_type.startswith('image/'):
                detected |= self.CONTENT_TYPES['FILE_ATTACHMENTS']
                break
        
        # 7. Check for embeds
        if message.embeds:
            detected |= self.CONTENT_TYPES['EMBEDS']
        
        return detected
    
    def get_content_type_names(self, flags: int) -> list:
        """Convert bitwise flags to human-readable content type names."""
        names = []
        for name, value in self.CONTENT_TYPES.items():
            if flags & value:
                names.append(name.lower().replace('_', ' '))
        return names
    
    async def on_message(self, message: discord.Message):
        """
        Core message handler that enforces granular channel restrictions.
        Supports both legacy restriction_type and new bitwise allowed/blocked flags.
        """
        if (
            message.author.bot
            or not message.guild
            or await self.is_bypass(message.author)
        ):
            return

        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)

        async with self.pool.acquire() as conn:
            # Fetch restriction configuration (both old and new columns)
            config = await conn.fetchrow(
                """SELECT restriction_type, redirect_channel_id, 
                          allowed_content_types, blocked_content_types 
                   FROM public.channel_restrictions_v2 
                   WHERE guild_id = $1 AND channel_id = $2""",
                guild_id,
                channel_id,
            )

        # If no configuration exists for this channel, do nothing
        if not config:
            return

        allowed_flags = config["allowed_content_types"] or 0
        blocked_flags = config["blocked_content_types"] or 0
        redirect_channel_id = config["redirect_channel_id"]

        try:
            # Detect what content types are in this message
            detected_content = self.detect_content_types(message)
            
            # If nothing detected (empty message), allow it
            if detected_content == 0:
                return
            
            # Check if any detected content is explicitly blocked
            if detected_content & blocked_flags:
                blocked_types = self.get_content_type_names(detected_content & blocked_flags)
                log.debug(f"Message blocked in {message.channel.name}: contains blocked content: {', '.join(blocked_types)}")
                await message.delete()
                
                # Send redirect message if configured
                if redirect_channel_id:
                    redirect_channel = self.bot.get_channel(int(redirect_channel_id))
                    if redirect_channel:
                        warn_msg = await message.channel.send(
                            f"🚫 {message.author.mention}, this channel doesn't allow **{', '.join(blocked_types)}**. "
                            f"Please use {redirect_channel.mention} instead."
                        )
                        await asyncio.sleep(15)
                        try:
                            await warn_msg.delete()
                        except:
                            pass
                return
            
            # If allowed list is set (non-zero), check if message contains ONLY allowed types
            if allowed_flags > 0:
                # Check if message contains any content NOT in the allowed list
                disallowed_content = detected_content & ~allowed_flags
                if disallowed_content:
                    disallowed_types = self.get_content_type_names(disallowed_content)
                    log.debug(f"Message blocked in {message.channel.name}: contains disallowed content: {', '.join(disallowed_types)}")
                    await message.delete()
                    
                    # Send redirect message if configured
                    if redirect_channel_id:
                        redirect_channel = self.bot.get_channel(int(redirect_channel_id))
                        if redirect_channel:
                            allowed_types = self.get_content_type_names(allowed_flags)
                            warn_msg = await message.channel.send(
                                f"🚫 {message.author.mention}, this channel only allows **{', '.join(allowed_types)}**. "
                                f"Please use {redirect_channel.mention} for other content."
                            )
                            await asyncio.sleep(15)
                            try:
                                await warn_msg.delete()
                            except:
                                pass
                    return

        except discord.Forbidden:
            log.warning(
                f"Missing permissions to delete message in channel {channel_id} (Guild: {guild_id})."
            )
        except discord.NotFound:
            # Message was deleted by another bot or moderator in the meantime
            pass
        except Exception as e:
            log.error(f"Error in NoTextManager on_message handler: {e}", exc_info=True)

    def register_commands(self):
        """Registers all slash commands for this manager."""

        @self.bot.tree.command(
            name="n1-setup-no-text",
            description="Configure a channel to only allow media and links (media-only).",
        )
        @app_commands.checks.has_permissions(manage_channels=True)
        async def setup_no_text(
            interaction: discord.Interaction,
            channel: discord.TextChannel,
            redirect_channel: discord.TextChannel,
        ):
            await interaction.response.defer(ephemeral=True)
            
            # Check if channel already has a restriction
            existing = await self.pool.fetchval(
                "SELECT id FROM public.channel_restrictions_v2 WHERE guild_id = $1 AND channel_id = $2",
                str(interaction.guild.id), str(channel.id)
            )
            
            if existing:
                await interaction.followup.send(
                    f"❌ {channel.mention} already has a restriction. Please remove it first.",
                    ephemeral=True
                )
                return

            query = """
                INSERT INTO public.channel_restrictions_v2 
                (guild_id, channel_id, channel_name, restriction_type, redirect_channel_id, redirect_channel_name, configured_by)
                VALUES ($1, $2, $3, 'media_only', $4, $5, $6)
            """
            await self.pool.execute(
                query,
                str(interaction.guild.id),
                str(channel.id),
                channel.name,
                str(redirect_channel.id),
                redirect_channel.name,
                str(interaction.user.id)
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
                "DELETE FROM public.channel_restrictions_v2 WHERE guild_id = $1 AND channel_id = $2 AND restriction_type = 'media_only'",
                str(interaction.guild.id),
                str(channel.id),
            )

            if "DELETE 1" in result:
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
            
            existing = await self.pool.fetchval(
                "SELECT id FROM public.channel_restrictions_v2 WHERE guild_id = $1 AND channel_id = $2",
                str(interaction.guild.id), str(channel.id)
            )
            
            if existing:
                await interaction.followup.send(
                    f"❌ {channel.mention} already has a restriction. Please remove it first.",
                    ephemeral=True
                )
                return

            query = """
                INSERT INTO public.channel_restrictions_v2 
                (guild_id, channel_id, channel_name, restriction_type, configured_by)
                VALUES ($1, $2, $3, 'block_invites', $4)
            """
            await self.pool.execute(query, str(interaction.guild.id), str(channel.id), channel.name, str(interaction.user.id))
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
            
            existing = await self.pool.fetchval(
                "SELECT id FROM public.channel_restrictions_v2 WHERE guild_id = $1 AND channel_id = $2",
                str(interaction.guild.id), str(channel.id)
            )
            
            if existing:
                await interaction.followup.send(
                    f"❌ {channel.mention} already has a restriction. Please remove it first.",
                    ephemeral=True
                )
                return

            query = """
                INSERT INTO public.channel_restrictions_v2 
                (guild_id, channel_id, channel_name, restriction_type, configured_by)
                VALUES ($1, $2, $3, 'block_all_links', $4)
            """
            await self.pool.execute(query, str(interaction.guild.id), str(channel.id), channel.name, str(interaction.user.id))
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
                "DELETE FROM public.channel_restrictions_v2 WHERE guild_id = $1 AND channel_id = $2 AND restriction_type = 'block_invites'",
                str(interaction.guild.id),
                str(channel.id),
            )

            if "DELETE 1" in result:
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
                "DELETE FROM public.channel_restrictions_v2 WHERE guild_id = $1 AND channel_id = $2 AND restriction_type = 'block_all_links'",
                str(interaction.guild.id),
                str(channel.id),
            )

            if "DELETE 1" in result:
                await interaction.followup.send(
                    f"✅ Removed the no-links rule from {channel.mention}.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"❌ {channel.mention} was not configured to block all links.",
                    ephemeral=True,
                )

        @self.bot.tree.command(
            name="n10-setup-text-only",
            description="Configure a channel to only allow plain text (no media).",
        )
        @app_commands.checks.has_permissions(manage_channels=True)
        async def setup_text_only(
            interaction: discord.Interaction,
            channel: discord.TextChannel,
            redirect_channel: discord.TextChannel,
        ):
            await interaction.response.defer(ephemeral=True)
            
            existing = await self.pool.fetchval(
                "SELECT id FROM public.channel_restrictions_v2 WHERE guild_id = $1 AND channel_id = $2",
                str(interaction.guild.id), str(channel.id)
            )
            
            if existing:
                await interaction.followup.send(
                    f"❌ {channel.mention} already has a restriction. Please remove it first.",
                    ephemeral=True
                )
                return

            query = """
                INSERT INTO public.channel_restrictions_v2 
                (guild_id, channel_id, channel_name, restriction_type, redirect_channel_id, redirect_channel_name, configured_by)
                VALUES ($1, $2, $3, 'text_only', $4, $5, $6)
            """
            await self.pool.execute(
                query,
                str(interaction.guild.id),
                str(channel.id),
                channel.name,
                str(redirect_channel.id),
                redirect_channel.name,
                str(interaction.user.id)
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
                "DELETE FROM public.channel_restrictions_v2 WHERE guild_id = $1 AND channel_id = $2 AND restriction_type = 'text_only'",
                str(interaction.guild.id),
                str(channel.id),
            )

            if "DELETE 1" in result:
                await interaction.followup.send(
                    f"✅ The text-only restriction has been removed from {channel.mention}.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"❌ {channel.mention} was not configured as a text-only channel.",
                    ephemeral=True,
                )

        log.info("💻 All No-Text commands registered.")
