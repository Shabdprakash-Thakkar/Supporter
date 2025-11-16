# Python_Files/youtube_notification.py

import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta
import asyncio
import asyncpg
import logging
import aiohttp
import feedparser

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


class YouTubeManager:
    """Manages YouTube notifications using RSS feeds (more reliable than API)."""

    def __init__(self, bot: commands.Bot, pool: asyncpg.Pool):
        self.bot = bot
        self.pool = pool
        self.session = None  # aiohttp session for RSS fetching
        log.info("YouTube Notification system (RSS) has been initialized.")

    async def start(self):
        """Initializes and starts the background task."""
        # Create aiohttp session for RSS requests
        self.session = aiohttp.ClientSession()
        self.check_for_videos.start()

    async def close(self):
        """Cleanup when bot shuts down."""
        if self.session:
            await self.session.close()

    # --- RSS Feed Fetching ---

    async def fetch_rss_feed(self, yt_channel_id: str):
        """Fetches and parses YouTube RSS feed for a channel."""
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={yt_channel_id}"

        try:
            async with self.session.get(rss_url, timeout=10) as response:
                if response.status != 200:
                    log.error(
                        f"RSS feed returned status {response.status} for channel {yt_channel_id}"
                    )
                    return None

                xml_content = await response.text()
                # Parse RSS feed (feedparser is synchronous, but fast)
                feed = await self.bot.loop.run_in_executor(
                    None, feedparser.parse, xml_content
                )
                return feed

        except asyncio.TimeoutError:
            log.error(f"Timeout fetching RSS feed for channel {yt_channel_id}")
            return None
        except Exception as e:
            log.error(f"Error fetching RSS feed for channel {yt_channel_id}: {e}")
            return None

    def extract_video_info(self, entry):
        """Extracts video information from RSS feed entry."""
        try:
            video_id = entry.get("yt_videoid")
            published_str = entry.get("published")

            if not video_id or not published_str:
                return None

            # Parse publish date
            published_at = datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%S%z")

            return {
                "video_id": video_id,
                "title": entry.get("title", "Untitled"),
                "link": entry.get(
                    "link", f"https://www.youtube.com/watch?v={video_id}"
                ),
                "channel_name": entry.get("author", "Unknown Channel"),
                "published_at": published_at,
            }
        except Exception as e:
            log.error(f"Error extracting video info from RSS entry: {e}")
            return None

    # --- Core Notification Logic ---

    @tasks.loop(minutes=15)
    async def check_for_videos(self):
        """
        The main loop that checks all configured channels for new videos.

        How RSS feeds work:
        - YouTube RSS feeds return the ~15 most recent videos
        - When a NEW video uploads, it appears at position 0
        - The oldest video (position 15) gets pushed out of the feed
        - Example: [Video1...Video15] → NEW upload → [NEW, Video1...Video14]

        This means:
        - We ALWAYS see new uploads (they're at the top)
        - Old videos eventually disappear from the feed
        - We only need to check what's currently in the feed

        Logic:
        1. Fetch RSS feed (returns ~15 latest videos)
        2. Check each video against database
        3. If NOT in database → NEW video → Check age → Notify if recent
        4. If in database → Already seen → Skip
        """
        log.info("Running YouTube RSS notification check...")

        configs = await self.pool.fetch(
            "SELECT * FROM public.youtube_notification_config WHERE is_enabled = TRUE"
        )
        if not configs:
            log.info("No active YouTube notification configurations found.")
            return

        for config in configs:
            guild_id_str = config["guild_id"]
            yt_channel_id = config["yt_channel_id"]

            try:
                # 1. Fetch RSS feed
                feed = await self.fetch_rss_feed(yt_channel_id)
                if not feed or not feed.entries:
                    log.warning(
                        f"No entries found in RSS feed for channel {yt_channel_id}"
                    )
                    continue

                log.debug(
                    f"Found {len(feed.entries)} videos in RSS feed for channel {yt_channel_id}"
                )

                # 2. Check ALL videos in feed against database
                # RSS typically returns the last 15 videos
                # We process all of them to catch any missed uploads
                for entry in feed.entries:
                    video_info = self.extract_video_info(entry)

                    if not video_info:
                        continue

                    video_id = video_info["video_id"]
                    published_at = video_info["published_at"]

                    # Calculate video age
                    age_days = (datetime.now(timezone.utc) - published_at).days

                    # 3. Check if this video is already in our database
                    # Fast query thanks to index on (guild_id, yt_channel_id, video_id)
                    log_exists = await self.pool.fetchval(
                        "SELECT 1 FROM public.youtube_notification_logs WHERE guild_id = $1 AND yt_channel_id = $2 AND video_id = $3",
                        guild_id_str,
                        yt_channel_id,
                        video_id,
                    )

                    if log_exists:
                        # Already seen this video, skip silently
                        continue

                    # 4. NEW VIDEO FOUND! This is not in our database yet
                    # But check if it's actually NEW or just an old video appearing in feed
                    if age_days > 2:
                        # This is an old video (>2 days) that somehow appeared in RSS
                        # Likely: YouTuber made old video public, or RSS glitch
                        # Action: Log it silently without notifying
                        log.info(
                            f"📦 Old video ({age_days} days) found in RSS for guild {guild_id_str}: {video_id} - Logging without notification"
                        )
                        await self.pool.execute(
                            "INSERT INTO public.youtube_notification_logs (guild_id, yt_channel_id, video_id, video_status) VALUES ($1, $2, $3, 'none') ON CONFLICT DO NOTHING",
                            guild_id_str,
                            yt_channel_id,
                            video_id,
                        )
                        continue

                    # 5. Actually NEW video (0-2 days old)
                    log.info(
                        f"🆕 New video detected for guild {guild_id_str} on channel {yt_channel_id}: {video_id} (uploaded {age_days} days ago)"
                    )

                    # Send notification
                    await self.send_notification(config, video_info)

                    # 5. Log to database to prevent future duplicates
                    await self.pool.execute(
                        "INSERT INTO public.youtube_notification_logs (guild_id, yt_channel_id, video_id, video_status) VALUES ($1, $2, $3, 'none') ON CONFLICT DO NOTHING",
                        guild_id_str,
                        yt_channel_id,
                        video_id,
                    )

                    # Small delay between notifications to avoid Discord rate limits
                    await asyncio.sleep(2)

            except Exception as e:
                log.error(
                    f"Unexpected error processing YouTube channel {yt_channel_id}: {e}",
                    exc_info=True,
                )

    async def send_notification(self, config: dict, video_info: dict):
        """Formats and sends the Discord notification message."""
        guild = self.bot.get_guild(int(config["guild_id"]))
        channel = self.bot.get_channel(int(config["target_channel_id"]))
        if not guild or not channel:
            return

        role = (
            guild.get_role(int(config["mention_role_id"]))
            if config["mention_role_id"]
            else None
        )
        mention = role.mention if role else "@here"

        video_id = video_info["video_id"]
        video_url = video_info["link"]
        title = video_info["title"]
        channel_name = video_info["channel_name"]

        message = f"🔔 {mention} **{channel_name}** just uploaded a new video!\n\n**{title}**\n{video_url}"

        try:
            await channel.send(message)
            log.info(
                f"✅ Sent notification for video {video_id} to guild {config['guild_id']}"
            )
        except discord.Forbidden:
            log.warning(
                f"Missing permissions to send YouTube notification in channel {channel.id} (Guild: {guild.id})"
            )
        except Exception as e:
            log.error(f"Failed to send YouTube notification: {e}")

    @check_for_videos.before_loop
    async def before_check_for_videos(self):
        """Aligns the loop to start on a clean 15-minute mark."""
        await self.bot.wait_until_ready()
        now = datetime.now(timezone.utc)
        minutes_to_wait = 15 - (now.minute % 15)
        seconds_to_wait = (minutes_to_wait * 60) - now.second
        log.info(
            f"Aligning YouTube check. Waiting {seconds_to_wait} seconds for first run."
        )
        await asyncio.sleep(seconds_to_wait)

    # --- Slash Commands ---

    def register_commands(self):

        @self.bot.tree.command(
            name="y1-find-youtube-channel-id",
            description="Find the Channel ID for a YouTube channel URL or @handle.",
        )
        @app_commands.describe(
            channel_url="YouTube channel URL or @handle (e.g., @MrBeast or youtube.com/c/MrBeast)"
        )
        async def find_youtube_channel_id(
            interaction: discord.Interaction, channel_url: str
        ):
            await interaction.response.defer(ephemeral=True)

            try:
                # Extract channel ID from various URL formats
                channel_id = None

                # Format 1: Already a channel ID (starts with UC)
                if channel_url.startswith("UC") and len(channel_url) == 24:
                    channel_id = channel_url

                # Format 2: Full URL with channel ID
                elif "/channel/" in channel_url:
                    channel_id = (
                        channel_url.split("/channel/")[1].split("/")[0].split("?")[0]
                    )

                # Format 3: Try fetching from custom URL or @handle
                else:
                    # Clean up the input
                    search_term = (
                        channel_url.replace("@", "")
                        .replace("https://", "")
                        .replace("www.youtube.com/", "")
                    )

                    # Try to fetch the RSS feed and extract channel ID from it
                    test_urls = [
                        f"https://www.youtube.com/@{search_term}",
                        f"https://www.youtube.com/c/{search_term}",
                        f"https://www.youtube.com/user/{search_term}",
                    ]

                    for test_url in test_urls:
                        try:
                            async with self.session.get(
                                test_url, timeout=5, allow_redirects=True
                            ) as response:
                                if response.status == 200:
                                    html = await response.text()
                                    # Extract channel ID from HTML
                                    if '"channelId":"' in html:
                                        channel_id = html.split('"channelId":"')[
                                            1
                                        ].split('"')[0]
                                        break
                        except:
                            continue

                if not channel_id or not channel_id.startswith("UC"):
                    await interaction.followup.send(
                        f"❌ Could not find channel ID. Please provide:\n"
                        f"• Direct channel URL: `youtube.com/channel/UC...`\n"
                        f"• Channel @handle: `@MrBeast`\n"
                        f"• Or the channel ID directly: `UC...`"
                    )
                    return

                # Verify the channel exists by fetching its RSS feed
                feed = await self.fetch_rss_feed(channel_id)
                if not feed or not feed.feed:
                    await interaction.followup.send(
                        f"❌ Could not verify channel with ID `{channel_id}`"
                    )
                    return

                channel_name = feed.feed.get("title", "Unknown Channel")

                embed = discord.Embed(title="🔍 YouTube Channel Found", color=0xFF0000)
                embed.add_field(name="Channel Name", value=channel_name, inline=False)
                embed.add_field(
                    name="Channel ID", value=f"`{channel_id}`", inline=False
                )
                embed.add_field(
                    name="RSS Feed",
                    value=f"[Click here](https://www.youtube.com/feeds/videos.xml?channel_id={channel_id})",
                    inline=False,
                )
                embed.set_footer(text="Copy the Channel ID for the setup command.")
                await interaction.followup.send(embed=embed)

            except Exception as e:
                log.error(f"Error in /y1-find-youtube-channel-id: {e}")
                await interaction.followup.send(
                    "❌ An error occurred. Please provide a valid YouTube channel URL or @handle."
                )

        @self.bot.tree.command(
            name="y2-setup-youtube-notifications",
            description="Set up notifications for a YouTube channel.",
        )
        @app_commands.checks.has_permissions(manage_guild=True)
        async def setup_notifications(
            interaction: discord.Interaction,
            youtube_channel_id: str,
            notification_channel: discord.TextChannel,
            role_to_mention: discord.Role,
        ):
            await interaction.response.defer(ephemeral=True)
            if not youtube_channel_id.startswith("UC"):
                await interaction.followup.send(
                    "❌ That doesn't look like a valid YouTube Channel ID. It should start with `UC`.\n"
                    "Use `/y1-find-youtube-channel-id` to get the correct ID."
                )
                return

            try:
                # Verify the channel exists by fetching its RSS feed
                feed = await self.fetch_rss_feed(youtube_channel_id)
                if not feed or not feed.feed:
                    await interaction.followup.send(
                        "❌ Could not find a YouTube channel with that ID. Please verify the ID is correct."
                    )
                    return

                yt_channel_name = feed.feed.get("title", "Unknown Channel")

                query = """
                    INSERT INTO public.youtube_notification_config (guild_id, yt_channel_id, target_channel_id, mention_role_id, guild_name, yt_channel_name, target_channel_name, mention_role_name)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (guild_id, yt_channel_id) DO UPDATE SET
                      target_channel_id = $3, mention_role_id = $4, updated_at = NOW(),
                      yt_channel_name = $6, target_channel_name = $7, mention_role_name = $8;
                """
                await self.pool.execute(
                    query,
                    str(interaction.guild.id),
                    youtube_channel_id,
                    str(notification_channel.id),
                    str(role_to_mention.id),
                    interaction.guild.name,
                    yt_channel_name,
                    notification_channel.name,
                    role_to_mention.name,
                )

                # AUTO-SEED: Mark ALL current videos in feed as "already seen"
                # This is THE KEY to preventing spam!
                # All videos currently in RSS feed are logged to database
                # Only FUTURE uploads will trigger notifications
                seeded_count = 0
                try:
                    if feed.entries:
                        log.info(
                            f"Auto-seeding {len(feed.entries)} videos for channel {youtube_channel_id}..."
                        )
                        for entry in feed.entries:
                            video_info = self.extract_video_info(entry)
                            if video_info:
                                video_id = video_info["video_id"]
                                result = await self.pool.execute(
                                    "INSERT INTO public.youtube_notification_logs (guild_id, yt_channel_id, video_id, video_status, notified_at) VALUES ($1, $2, $3, 'none', NOW()) ON CONFLICT DO NOTHING",
                                    str(interaction.guild.id),
                                    youtube_channel_id,
                                    video_id,
                                )
                                if "INSERT" in result:
                                    seeded_count += 1
                        log.info(
                            f"✅ Auto-seeded {seeded_count} videos for channel {youtube_channel_id}"
                        )
                except Exception as seed_error:
                    log.warning(f"Could not auto-seed videos: {seed_error}")

                await interaction.followup.send(
                    f"✅ **Setup Complete!**\n\n"
                    f"📺 **Channel:** {yt_channel_name}\n"
                    f"📢 **Notifications:** {notification_channel.mention}\n"
                    f"🏷️ **Mention:** {role_to_mention.mention}\n"
                    f"📦 **Auto-seeded:** {seeded_count} existing videos marked as seen\n\n"
                    f"🔔 **Only NEW videos** uploaded after now will trigger notifications!\n"
                    f"🔄 **Method:** RSS feeds (no API quota limits)"
                )
            except Exception as e:
                log.error(f"Error in /y2-setup: {e}", exc_info=True)
                await interaction.followup.send(
                    "❌ An error occurred during setup. Please check the channel ID and my permissions."
                )

        @self.bot.tree.command(
            name="y3-disable-youtube-notifications",
            description="Disable YouTube notifications for a channel.",
        )
        @app_commands.checks.has_permissions(manage_guild=True)
        async def disable_notifications(
            interaction: discord.Interaction, youtube_channel_id: str
        ):
            await interaction.response.defer(ephemeral=True)
            result = await self.pool.execute(
                "DELETE FROM public.youtube_notification_config WHERE guild_id = $1 AND yt_channel_id = $2",
                str(interaction.guild.id),
                youtube_channel_id,
            )
            if result == "DELETE 1":
                await interaction.followup.send(
                    f"✅ Notifications for the YouTube channel `{youtube_channel_id}` have been disabled."
                )
            else:
                await interaction.followup.send(
                    f"❌ No notification setup was found for that YouTube channel ID in this server."
                )

        @self.bot.tree.command(
            name="y4-bulk-seed-all-videos",
            description="[ADMIN] Seed ALL videos from a channel (uses API quota). Run once per channel.",
        )
        @app_commands.checks.has_permissions(administrator=True)
        @app_commands.describe(
            youtube_channel_id="The YouTube Channel ID",
            max_videos="Maximum videos to seed (default: 50, max: 200)",
        )
        async def bulk_seed_all_videos(
            interaction: discord.Interaction,
            youtube_channel_id: str,
            max_videos: int = 50,
        ):
            """
            Seeds ALL videos from a channel (videos, shorts, live streams).
            Uses API if available, otherwise uses RSS pagination trick.
            """
            await interaction.response.defer(ephemeral=True)

            if not youtube_channel_id.startswith("UC"):
                await interaction.followup.send("❌ Invalid YouTube Channel ID format.")
                return

            if max_videos < 1 or max_videos > 200:
                await interaction.followup.send(
                    "❌ max_videos must be between 1 and 200."
                )
                return

            try:
                # Try to get ALL videos using RSS + pagination
                # RSS gives us ~15 at a time, but we can't truly paginate
                # So we'll just seed what we can get
                feed = await self.fetch_rss_feed(youtube_channel_id)
                if not feed or not feed.entries:
                    await interaction.followup.send(
                        "❌ Could not fetch videos for this channel."
                    )
                    return

                channel_name = feed.feed.get("title", "Unknown Channel")

                # Seed all videos from RSS feed
                seeded_count = 0
                skipped_count = 0

                for entry in feed.entries[:max_videos]:
                    video_info = self.extract_video_info(entry)
                    if not video_info:
                        continue

                    video_id = video_info["video_id"]
                    result = await self.pool.execute(
                        "INSERT INTO public.youtube_notification_logs (guild_id, yt_channel_id, video_id, video_status, notified_at) VALUES ($1, $2, $3, 'none', NOW() - INTERVAL '90 days') ON CONFLICT DO NOTHING",
                        str(interaction.guild.id),
                        youtube_channel_id,
                        video_id,
                    )
                    if "INSERT" in result:
                        seeded_count += 1
                    else:
                        skipped_count += 1

                embed = discord.Embed(
                    title="📦 Bulk Seed Complete",
                    description=f"Channel: **{channel_name}**",
                    color=0x00FF00,
                )
                embed.add_field(name="✅ Seeded", value=str(seeded_count), inline=True)
                embed.add_field(
                    name="⏭️ Skipped (already in DB)",
                    value=str(skipped_count),
                    inline=True,
                )
                embed.add_field(
                    name="ℹ️ Note",
                    value="RSS feeds only provide ~15 recent videos. For complete history, use YouTube Data API manually or wait for videos to naturally appear in feed over time.",
                    inline=False,
                )
                embed.set_footer(text=f"Channel ID: {youtube_channel_id}")

                await interaction.followup.send(embed=embed)
                log.info(
                    f"Bulk seeded {seeded_count} videos for channel {youtube_channel_id} in guild {interaction.guild.id}"
                )

            except Exception as e:
                log.error(f"Error in /y4-bulk-seed-all-videos: {e}")
                await interaction.followup.send(
                    "❌ An error occurred during bulk seeding."
                )

        @self.bot.tree.command(
            name="y5-test-rss-feed",
            description="Test the RSS feed for a YouTube channel and see what videos would be processed.",
        )
        @app_commands.checks.has_permissions(manage_guild=True)
        @app_commands.describe(youtube_channel_id="The YouTube Channel ID to test")
        async def test_rss_feed(
            interaction: discord.Interaction, youtube_channel_id: str
        ):
            await interaction.response.defer(ephemeral=True)

            if not youtube_channel_id.startswith("UC"):
                await interaction.followup.send("❌ Invalid YouTube Channel ID format.")
                return

            try:
                # Fetch RSS feed
                feed = await self.fetch_rss_feed(youtube_channel_id)
                if not feed or not feed.entries:
                    await interaction.followup.send(
                        "❌ Could not fetch RSS feed for this channel."
                    )
                    return

                channel_name = feed.feed.get("title", "Unknown Channel")

                embed = discord.Embed(
                    title=f"📡 RSS Feed Test: {channel_name}",
                    description=f"Found **{len(feed.entries)}** videos in RSS feed",
                    color=0xFF0000,
                )

                # Show first 5 videos
                for i, entry in enumerate(feed.entries[:5]):
                    video_info = self.extract_video_info(entry)
                    if video_info:
                        age_days = (
                            datetime.now(timezone.utc) - video_info["published_at"]
                        ).days

                        # Check if in database
                        in_db = await self.pool.fetchval(
                            "SELECT 1 FROM public.youtube_notification_logs WHERE guild_id = $1 AND yt_channel_id = $2 AND video_id = $3",
                            str(interaction.guild.id),
                            youtube_channel_id,
                            video_info["video_id"],
                        )

                        status = (
                            "✅ In database (will skip)"
                            if in_db
                            else "🆕 NEW - Would notify!"
                        )

                        embed.add_field(
                            name=f"{i+1}. {video_info['title'][:50]}...",
                            value=f"Age: {age_days} days ago | {status}\nID: `{video_info['video_id']}`",
                            inline=False,
                        )

                embed.set_footer(
                    text=f"Channel ID: {youtube_channel_id} | Only videos NOT in database trigger notifications"
                )
                await interaction.followup.send(embed=embed)

            except Exception as e:
                log.error(f"Error in /y4-test-rss-feed: {e}")
                await interaction.followup.send(
                    "❌ An error occurred while testing the RSS feed."
                )

        log.info("💻 YouTube Notification commands (RSS) registered.")
