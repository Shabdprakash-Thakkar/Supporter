# Python_Files/help.py

import discord
from discord.ext import commands
from datetime import datetime, timezone
import logging

log = logging.getLogger(__name__)


class HelpManager:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log.info("Help system has been initialized.")

    def register_commands(self):
        """Registers the /g1-help slash command."""

        @self.bot.tree.command(
            name="g1-help",
            description="Show instructions and a complete list of commands.",
        )
        async def help_command(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)

            embed = discord.Embed(
                title="🤖 Supporter Bot Help",
                description="Complete list of available commands organized by category.",
                color=discord.Color.from_rgb(0, 255, 0),
                timestamp=datetime.now(timezone.utc),
            )

            embed.add_field(
                name="📊 Leveling System (10 commands)",
                value=(
                    "`/l1-level` → Check your or another user's level and XP.\n"
                    "`/l2-leaderboard` → Show the top 10 users in the server.\n"
                    "`/l3-setup-level-reward` → Set a role reward for a specific level.\n"
                    "`/l4-level-reward-show` → Display all configured level rewards.\n"
                    "`/l5-notify-level-msg` → Set the channel for level-up announcements.\n"
                    "`/l6-set-auto-reset` → Schedule automatic XP resets (1-365 days).\n"
                    "`/l7-show-auto-reset` → Show the current auto-reset configuration.\n"
                    "`/l8-stop-auto-reset` → Disable the automatic XP reset.\n"
                    "`/l9-reset-xp` → Manually reset all XP and reward roles immediately.\n"
                    "`/l10-upgrade-all-roles` → Manually sync roles for all users."
                ),
                inline=False,
            )

            embed.add_field(
                name="📢 YouTube Notifications (5 commands)",
                value=(
                    "`/y1-find-youtube-channel-id` → Find a channel's ID from its @handle.\n"
                    "`/y2-setup-youtube-notifications` → Set up notifications for a YT channel.\n"
                    "`/y3-disable-youtube-notifications` → Stop notifications for a YT channel.\n"
                    "`/y4-bulk-seed-all-videos` → [ADMIN] Seed existing videos for a channel (bulk).\n"
                    "`/y5-test-rss-feed` → [ADMIN] Test a channel's RSS feed and preview what would be processed."
                ),
                inline=False,
            )

            embed.add_field(
                name="🚫📝 Channel Restrictions (11 commands)",
                value=(
                    "**Media-Only Channels:**\n"
                    "`/n1-setup-no-text` → Configure a media-only channel.\n"
                    "`/n2-remove-no-text` → Remove media-only restrictions.\n\n"
                    "**Text-Only Channels:**\n"
                    "`/n10-setup-text-only` → Configure a text-only channel (no attachments/embeds).\n"
                    "`/n11-remove-text-only` → Remove text-only restrictions.\n\n"
                    "**Link Control:**\n"
                    "`/n6-no-discord-link` → Block Discord invite links only.\n"
                    "`/n7-no-links` → Block ALL links.\n"
                    "`/n8-remove-no-discord-link` → Stop blocking Discord links.\n"
                    "`/n9-remove-no-links` → Stop blocking all links.\n\n"
                    "**Bypass System:**\n"
                    "`/n3-bypass-no-text` → Allow a role to bypass restrictions.\n"
                    "`/n4-show-bypass-roles` → Show roles that can bypass.\n"
                    "`/n5-remove-bypass-role` → Remove a role's bypass ability."
                ),
                inline=False,
            )

            embed.add_field(
                name="⏰ Time & Date Channels (1 command)",
                value=(
                    "`/t1-setup-time-channels` → Set up date, India, and Japan time channels."
                ),
                inline=False,
            )

            embed.add_field(
                name="⚙️ General Commands (2 commands)",
                value=(
                    "`/g1-help` → Show this help message.\n"
                    "`/g2-show-config` → Show current bot configuration for this server."
                ),
                inline=False,
            )

            if await self.bot.is_owner(interaction.user):
                embed.add_field(
                    name="👑 Owner Commands (4 commands)",
                    value=(
                        "`/g3-serverlist` → Lists all servers the bot is in.\n"
                        "`/g4-leaveserver` → Force the bot to leave a server.\n"
                        "`/g5-banguild` → Ban a server from using the bot.\n"
                        "`/g6-unbanguild` → Unban a server."
                    ),
                    inline=False,
                )

            embed.set_footer(
                text=f"Server: {interaction.guild.name} | Total: 33 commands",
                icon_url=interaction.guild.icon.url if interaction.guild.icon else None,
            )

            await interaction.followup.send(embed=embed)

        log.info("💻 Help command registered.")
