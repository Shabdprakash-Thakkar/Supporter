document.addEventListener("DOMContentLoaded", function () {
  if (typeof GUILD_ID !== "undefined") {
    loadDashboardData();
    initializeEventListeners();
  }
});

/**
 * Main data loading function. Fetches server config and live Discord data.
 */
async function loadDashboardData() {
  showLoader("general-settings-loader", "general-settings-content");
  showLoader("time-channels-loader", "time-channels-content");
  showLoader("youtube-loader", "youtube-configs-container");

  try {
    const [configRes, discordDataRes] = await Promise.all([
      fetch(`/api/server/${GUILD_ID}/config`),
      fetch(`/api/server/${GUILD_ID}/discord-data`),
    ]);

    if (!configRes.ok) {
      const errText = await configRes.text();
      throw new Error(`Config API (${configRes.status}): ${errText}`);
    }
    if (!discordDataRes.ok) {
      const errText = await discordDataRes.text();
      throw new Error(`Discord Data API (${discordDataRes.status}): ${errText}`);
    }

    const config = await configRes.json();
    const discordData = await discordDataRes.json();

    if (config.error) throw new Error(config.error);
    if (discordData.error) throw new Error(discordData.error);

    // Populate all sections
    try { populateGeneralSettings(config.guild_settings); } catch (e) { console.error("Error in populateGeneralSettings:", e); }
    try { populateLevelingTab(config, discordData); } catch (e) { console.error("Error in populateLevelingTab:", e); }
    try { populateTimeChannels(config.time_channel_config, discordData.channels); } catch (e) { console.error("Error in populateTimeChannels:", e); }
    try { populateRewardModal(discordData.roles); } catch (e) { console.error("Error in populateRewardModal:", e); }
    try { populateYouTubeTab(config, discordData); } catch (e) { console.error("Error in populateYouTubeTab:", e); }

    // Channel restrictions are now handled in a separate iframe/tab
    // populateChannelRestrictions(discordData.channels, config.channel_restrictions);

    loadLeaderboard();
  } catch (error) {
    console.error("❌ Fatal error loading dashboard data:", error);
    showToast(`Error loading dashboard data: ${error.message}`, "danger");
  } finally {
    hideLoader("general-settings-loader", "general-settings-content");
    hideLoader("time-channels-loader", "time-channels-content");
    hideLoader("youtube-loader", "youtube-configs-container");
  }
}

// ==================== UI POPULATION FUNCTIONS ====================

function populateGeneralSettings(settings) {
  document.getElementById("xp_per_message").value = settings.xp_per_message;
  document.getElementById("xp_per_image").value = settings.xp_per_image;
  document.getElementById("xp_per_minute_in_voice").value =
    settings.xp_per_minute_in_voice;
  document.getElementById("voice_xp_limit").value = settings.voice_xp_limit;
}

function populateLevelingTab(config, discordData) {
  const { level_rewards, level_notify_channel_id } = config;
  const { roles, channels } = discordData;

  // Level Rewards List
  const rewardsContainer = document.getElementById("level-rewards-list");
  if (!level_rewards || level_rewards.length === 0) {
    rewardsContainer.innerHTML = `<div class="text-center text-muted py-4">No level rewards configured.</div>`;
  } else {
    const roleMap = new Map(roles.map((r) => [r.id, r.name]));
    rewardsContainer.innerHTML = level_rewards
      .map(
        (reward) => `
            <div class="reward-item p-3 mb-2 rounded-3 d-flex justify-content-between align-items-center">
                <div><strong>Level ${reward.level
          }</strong> &rarr; <span class="badge bg-primary">${roleMap.get(reward.role_id) || "Unknown Role"
          }</span></div>
                <div>
                    <button class="btn btn-sm btn-outline-secondary me-2 edit-reward-btn" data-level="${reward.level
          }" data-role-id="${reward.role_id
          }" title="Edit"><i class="fas fa-pencil-alt"></i></button>
                    <button class="btn btn-sm btn-outline-danger delete-reward-btn" data-level="${reward.level
          }" title="Delete"><i class="fas fa-trash"></i></button>
                </div>
            </div>`
      )
      .join("");
  }

  // Notification Channel Select
  const notifySelect = document.getElementById("level-notify-channel-select");
  const textChannels = channels.filter((c) => c.type === 0);
  notifySelect.innerHTML =
    '<option value="">-- Disable Notifications --</option>' +
    textChannels
      .map(
        (c) =>
          `<option value="${c.id}" ${level_notify_channel_id === c.id ? "selected" : ""
          }>#${c.name}</option>`
      )
      .join("");

  // Show notification channel content and hide loader
  hideLoader("level-notify-channel-loader", "level-notify-channel-content");

  // Load auto-reset configuration
  loadAutoResetConfig();
  console.log("✅ Leveling tab populated, auto-reset config loaded");
}

function populateTimeChannels(config, allChannels) {
  const voiceChannels = allChannels.filter((c) => c.type === 2);
  const selectors = [
    { id: "date-channel-select", key: "date_channel_id" },
    { id: "india-channel-select", key: "india_channel_id" },
    { id: "japan-channel-select", key: "japan_channel_id" },
  ];
  document.getElementById("time-channels-enabled").checked = config.is_enabled;
  selectors.forEach((sel) => {
    const selectEl = document.getElementById(sel.id);
    selectEl.innerHTML =
      '<option value="">-- None --</option>' +
      voiceChannels
        .map((c) => `<option value="${c.id}">${c.name}</option>`)
        .join("");
    selectEl.value = config[sel.key] || "";
  });
}

function populateRewardModal(roles) {
  const rewardRoleSelect = document.getElementById("reward-role-select");
  rewardRoleSelect.innerHTML =
    '<option value="" selected disabled>-- Select a Role --</option>' +
    roles.map((r) => `<option value="${r.id}">${r.name}</option>`).join("");
}

// ==================== AUTO RESET CONFIGURATION ====================
async function loadAutoResetConfig() {
  const statusCard = document.getElementById("auto-reset-status-card");
  const statusTitle = document.getElementById("auto-reset-status-title");
  const statusDetails = document.getElementById("auto-reset-status-details");
  const disableBtn = document.getElementById("disable-auto-reset-btn");
  const enableBtn = document.getElementById("enable-auto-reset-btn");
  const daysInput = document.getElementById("auto-reset-days");

  // Show loading state
  if (statusTitle) {
    statusTitle.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Loading...';
  }
  if (statusDetails) {
    statusDetails.textContent = 'Please wait...';
  }

  try {
    console.log(`🔍 Fetching auto-reset config for guild: ${GUILD_ID}`);
    
    const response = await fetch(`/api/server/${GUILD_ID}/auto-reset`);
    
    console.log(`📡 Response status: ${response.status}`);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    console.log("📦 Auto-reset data received:", data);

    if (data.enabled) {
      // Auto-reset is ENABLED
      statusCard.classList.remove("alert-secondary", "alert-danger");
      statusCard.classList.add("alert-success");

      // Parse dates
      const nextResetDate = new Date(data.next_reset);
      const lastResetDate = new Date(data.last_reset);
      
      // Format dates in IST
      const istOptions = { 
        timeZone: 'Asia/Kolkata', 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
      };
      
      const lastResetIST = lastResetDate.toLocaleString('en-IN', istOptions);
      const nextResetIST = nextResetDate.toLocaleString('en-IN', istOptions);

      statusTitle.innerHTML = `
        <i class="fas fa-check-circle text-success me-2"></i>
        Auto-Reset Active — Every ${data.days} Day${data.days > 1 ? 's' : ''}
      `;

      statusDetails.innerHTML = `
        <div class="mt-2">
          <div><i class="fas fa-history me-2"></i><strong>Last Reset:</strong> ${lastResetIST} IST</div>
          <div><i class="fas fa-clock me-2"></i><strong>Next Reset:</strong> ${nextResetIST} IST</div>
          <div class="mt-2 text-warning">
            <i class="fas fa-hourglass-half me-2"></i>
            <strong>Time Remaining:</strong> ${data.days_remaining} day${data.days_remaining !== 1 ? 's' : ''} 
            and ${data.hours_remaining} hour${data.hours_remaining !== 1 ? 's' : ''}
          </div>
        </div>
      `;

      // Show disable button
      if (disableBtn) {
        disableBtn.classList.remove("d-none");
      }
      
      // Update enable button text
      if (enableBtn) {
        enableBtn.innerHTML = '<i class="fas fa-edit me-2"></i>Update Schedule';
      }
      
      // Set input value
      if (daysInput) {
        daysInput.value = data.days;
        daysInput.placeholder = `Currently: ${data.days} days`;
      }

      console.log("✅ Auto-reset status displayed successfully");

    } else {
      // Auto-reset is DISABLED
      statusCard.classList.remove("alert-success", "alert-danger");
      statusCard.classList.add("alert-secondary");

      statusTitle.innerHTML = `
        <i class="fas fa-pause-circle text-secondary me-2"></i>
        Auto-Reset Not Configured
      `;
      
      statusDetails.innerHTML = `
        <span class="text-muted">Set up automatic XP resets using the form below.</span>
      `;

      // Hide disable button
      if (disableBtn) {
        disableBtn.classList.add("d-none");
      }
      
      // Reset enable button
      if (enableBtn) {
        enableBtn.innerHTML = '<i class="fas fa-play me-2"></i>Enable Auto-Reset';
      }
      
      // Clear input
      if (daysInput) {
        daysInput.value = "";
        daysInput.placeholder = "e.g., 30 for monthly";
      }

      console.log("ℹ️ No auto-reset configured");
    }

  } catch (error) {
    console.error("❌ Error loading auto-reset config:", error);
    
    statusCard.classList.remove("alert-success", "alert-secondary");
    statusCard.classList.add("alert-danger");
    
    statusTitle.innerHTML = `
      <i class="fas fa-exclamation-circle text-danger me-2"></i>
      Error Loading Configuration
    `;
    
    statusDetails.innerHTML = `
      <span class="text-danger">${error.message}</span>
      <br>
      <button class="btn btn-sm btn-outline-danger mt-2" onclick="loadAutoResetConfig()">
        <i class="fas fa-sync me-1"></i>Retry
      </button>
    `;
  }
}

async function enableAutoReset() {
  const daysInput = document.getElementById("auto-reset-days");
  const days = parseInt(daysInput.value);

  if (!days || days < 1 || days > 365) {
    showToast("Please enter a valid number of days (1-365)", "danger");
    daysInput.focus();
    return;
  }

  const btn = document.getElementById("enable-auto-reset-btn");
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Saving...';

  try {
    const response = await fetch(`/api/server/${GUILD_ID}/auto-reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ days }),
    });

    const result = await response.json();
    
    if (!response.ok) {
      throw new Error(result.error || "Failed to enable auto-reset");
    }

    showToast(`✅ Auto-reset enabled! XP will reset every ${days} day${days > 1 ? 's' : ''}.`, "success");
    
    // Reload the configuration to show updated status
    await loadAutoResetConfig();

  } catch (error) {
    console.error("Error enabling auto-reset:", error);
    showToast(`❌ Error: ${error.message}`, "danger");
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
}

async function disableAutoReset() {
  if (!confirm("Are you sure you want to disable automatic XP resets?\n\nThis will stop the scheduled reset, but won't affect current XP values.")) {
    return;
  }

  const btn = document.getElementById("disable-auto-reset-btn");
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Stopping...';

  try {
    const response = await fetch(`/api/server/${GUILD_ID}/auto-reset`, {
      method: "DELETE",
    });

    const result = await response.json();
    
    if (!response.ok) {
      throw new Error(result.error || "Failed to disable auto-reset");
    }

    showToast("✅ Auto-reset has been disabled.", "success");
    
    // Reload the configuration to show updated status
    await loadAutoResetConfig();

  } catch (error) {
    console.error("Error disabling auto-reset:", error);
    showToast(`❌ Error: ${error.message}`, "danger");
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
}

async function manualResetXP() {
  const btn = document.getElementById("confirm-manual-reset-btn");
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Resetting...';

  try {
    const response = await fetch(`/api/server/${GUILD_ID}/reset-xp`, {
      method: "POST",
    });

    const result = await response.json();
    
    if (!response.ok) {
      throw new Error(result.error || "Failed to reset XP");
    }

    showToast(`✅ ${result.message}`, "success");

    // Close modal
    const modal = bootstrap.Modal.getInstance(document.getElementById("confirmResetModal"));
    if (modal) modal.hide();

    // Reload leaderboard to show reset
    loadLeaderboard();
    
    // Reload auto-reset config (last_reset timestamp updated)
    loadAutoResetConfig();

  } catch (error) {
    console.error("Error resetting XP:", error);
    showToast(`❌ Error: ${error.message}`, "danger");
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
}

// ==================== YOUTUBE NOTIFICATION FUNCTIONS ====================

function populateYouTubeTab(config, discordData) {
  const container = document.getElementById("youtube-configs-container");
  const loader = document.getElementById("youtube-loader");

  const channelSelect = document.getElementById("yt-discord-channel-select");
  const roleSelect = document.getElementById("yt-mention-role-select");

  const textChannels = discordData.channels.filter((c) => c.type === 0);
  channelSelect.innerHTML =
    '<option selected disabled value="">-- Select a channel --</option>' +
    textChannels
      .map((c) => `<option value="${c.id}">#${c.name}</option>`)
      .join("");
  roleSelect.innerHTML =
    '<option value="">-- No Role Mention --</option>' +
    discordData.roles
      .map((r) => `<option value="${r.id}">@${r.name}</option>`)
      .join("");

  const ytConfigs = config.youtube_notification_config || [];

  // Hide loader first
  if (loader) loader.style.display = "none";

  // Show container and populate it
  if (container) {
    container.style.display = "block";
    container.classList.remove("d-none");

    if (ytConfigs.length === 0) {
      container.innerHTML = `
        <div class="text-center text-muted py-5">
          <i class="fab fa-youtube fa-3x mb-3 opacity-50"></i>
          <p class="mb-0">No YouTube notifications configured.</p>
          <small>Click "Add New Notification" to get started.</small>
        </div>`;
    } else {
      container.innerHTML = ytConfigs
        .map((ytConfig) => {
          const channelName =
            discordData.channels.find(
              (c) => c.id === ytConfig.target_channel_id
            )?.name || "Unknown Channel";
          const roleName = ytConfig.mention_role_id
            ? discordData.roles.find((r) => r.id === ytConfig.mention_role_id)
              ?.name || "Unknown Role"
            : "here";
          return `
            <div class="card mb-3 shadow-sm">
              <div class="card-body d-flex justify-content-between align-items-center flex-wrap">
                <div class="mb-2 mb-md-0">
                  <h5 class="card-title mb-1">
                    <i class="fab fa-youtube text-danger me-2"></i>${ytConfig.yt_channel_name
            }
                  </h5>
                  <p class="card-text small text-muted mb-0">
                    <i class="fas fa-hashtag me-1"></i>${channelName} 
                    <span class="mx-2">•</span>
                    <i class="fas fa-at me-1"></i>${roleName}
                  </p>
                </div>
                <div class="d-flex gap-2 mt-2 mt-md-0">
                  <button class="btn btn-sm btn-outline-primary edit-yt-btn" data-config='${JSON.stringify(
              ytConfig
            ).replace(/'/g, "&#39;")}'>
                    <i class="fas fa-pencil-alt me-1"></i> Edit
                  </button>
                  <button class="btn btn-sm btn-outline-danger delete-yt-btn" 
                    data-yt-channel-id="${ytConfig.yt_channel_id}" 
                    data-yt-channel-name="${ytConfig.yt_channel_name}">
                    <i class="fas fa-trash me-1"></i> Delete
                  </button>
                </div>
              </div>
            </div>`;
        })
        .join("");
    }
  }
}

async function saveYtNotification(event) {
  event.preventDefault();
  const btn = document.getElementById("save-yt-notification-btn");
  const originalBtnText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Saving...';

  const channelInfo = document.getElementById(
    "yt-channel-finder-status"
  ).dataset;

  const data = {
    yt_channel_id: channelInfo.channelId,
    yt_channel_name: channelInfo.channelName,
    target_channel_id: document.getElementById("yt-discord-channel-select")
      .value,
    mention_role_id:
      document.getElementById("yt-mention-role-select").value || null,
    custom_message: document.getElementById("yt-custom-message").value,
  };

  if (!data.yt_channel_id || !data.yt_channel_name) {
    showToast("Please find and verify a YouTube channel first.", "danger");
    btn.disabled = false;
    btn.innerHTML = originalBtnText;
    return;
  }

  if (!data.target_channel_id) {
    showToast("Please select a Discord channel for notifications.", "danger");
    btn.disabled = false;
    btn.innerHTML = originalBtnText;
    return;
  }

  if (!data.custom_message || data.custom_message.trim() === "") {
    showToast("Please enter a custom notification message.", "danger");
    btn.disabled = false;
    btn.innerHTML = originalBtnText;
    return;
  }

  try {
    const response = await fetch(`/api/server/${GUILD_ID}/youtube-configs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || "Failed to save configuration");
    }

    // Handle successful save
    console.log("✅ YouTube notification saved:", result);

    // Close modal
    const modal = bootstrap.Modal.getInstance(
      document.getElementById("addYtNotificationModal")
    );
    if (modal) {
      modal.hide();
    }

    // Show success message with seeding info
    if (result.is_new_setup && result.seeding) {
      const seedingInfo = result.seeding;

      if (seedingInfo.success) {
        showToast(
          `✅ YouTube notification created for ${data.yt_channel_name}!\n\n` +
            `📦 Seeded ${seedingInfo.total_seeded} videos:\n` +
            `• ${seedingInfo.skipped_old} old videos (no notification)\n` +
            `• ${seedingInfo.recent_videos} recent videos (will notify on next upload)`,
          "success",
          8000 // Show for 8 seconds
        );
      } else {
        // Seeding failed but config was saved
        showToast(
          `✅ YouTube notification created for ${data.yt_channel_name}!\n\n` +
            `⚠️ Video seeding failed: ${seedingInfo.error}\n` +
            `Notifications will still work for new uploads.`,
          "warning",
          8000
        );
      }
    } else {
      showToast(
        `✅ YouTube notification ${
          result.is_new_setup ? "created" : "updated"
        } successfully!`,
        "success"
      );
    }

    // Reload YouTube configs
    loadDashboardData();
  } catch (error) {
    console.error("❌ Error saving YouTube notification:", error);
    showToast(`❌ Error: ${error.message}`, "danger");
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalBtnText;
  }
}

async function deleteYtNotification(ytChannelId, ytChannelName) {
  if (
    !confirm(
      `Are you sure you want to delete notifications for "${ytChannelName}"?`
    )
  ) {
    return;
  }

  try {
    const response = await fetch(
      `/api/server/${GUILD_ID}/youtube-configs?yt_channel_id=${ytChannelId}`,
      {
        method: "DELETE",
      }
    );
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);

    showToast("YouTube notification deleted!", "success");
    loadDashboardData();
  } catch (error) {
    showToast(`Error: ${error.message}`, "danger");
  }
}

// ==================== EVENT LISTENERS (UNIFIED) ====================

function initializeEventListeners() {
  // ==================== GENERAL SETTINGS ====================
  const generalForm = document.getElementById("general-settings-form");
  if (generalForm) {
    generalForm.addEventListener("submit", saveGeneralSettings);
  }

  // ==================== TIME CHANNELS ====================
  const timeChannelsForm = document.getElementById("time-channels-form");
  if (timeChannelsForm) {
    timeChannelsForm.addEventListener("submit", saveTimeChannels);
  }

  // ==================== LEVELING TAB ====================

  // Level reward form
  const levelRewardForm = document.getElementById("level-reward-form");
  if (levelRewardForm) {
    levelRewardForm.addEventListener("submit", saveLevelReward);
  }

  // Notification channel save button
  const saveNotifyBtn = document.getElementById("save-notify-channel-btn");
  if (saveNotifyBtn) {
    saveNotifyBtn.addEventListener("click", saveLevelNotifyChannel);
  }

  // ==================== AUTO-RESET SECTION ====================

  // Enable auto-reset button
  const enableAutoResetBtn = document.getElementById("enable-auto-reset-btn");
  if (enableAutoResetBtn) {
    enableAutoResetBtn.addEventListener("click", enableAutoReset);
    console.log("✅ Enable auto-reset button listener attached");
  } else {
    console.warn("⚠️ enable-auto-reset-btn not found");
  }

  // Disable auto-reset button
  const disableAutoResetBtn = document.getElementById("disable-auto-reset-btn");
  if (disableAutoResetBtn) {
    disableAutoResetBtn.addEventListener("click", disableAutoReset);
    console.log("✅ Disable auto-reset button listener attached");
  } else {
    console.warn("⚠️ disable-auto-reset-btn not found");
  }

  // Manual reset confirmation button
  const confirmResetBtn = document.getElementById("confirm-manual-reset-btn");
  if (confirmResetBtn) {
    confirmResetBtn.addEventListener("click", manualResetXP);
    console.log("✅ Manual reset button listener attached");
  }

  // Auto-reset days input - allow Enter key
  const autoResetDaysInput = document.getElementById("auto-reset-days");
  if (autoResetDaysInput) {
    autoResetDaysInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        enableAutoReset();
      }
    });
    console.log("✅ Auto-reset days input listener attached");
  } else {
    console.warn("⚠️ auto-reset-days input not found");
  }

  // ==================== TAB CHANGE DETECTION ====================

  // Detect when user switches to the "Settings" sub-tab under Leveling
  const levelSettingsTab = document.querySelector(
    'button[data-bs-target="#level-settings"]'
  );
  if (levelSettingsTab) {
    levelSettingsTab.addEventListener("shown.bs.tab", function (e) {
      console.log("🔄 Level Settings tab shown - reloading auto-reset config");
      loadAutoResetConfig();
    });
  }

  // ==================== LEADERBOARD ====================

  let debounceTimer;
  const leaderboardSearch = document.getElementById("leaderboard-search");
  if (leaderboardSearch) {
    leaderboardSearch.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(loadLeaderboard, 300);
    });
  }

  const leaderboardLimit = document.getElementById("leaderboard-limit");
  if (leaderboardLimit) {
    leaderboardLimit.addEventListener("change", loadLeaderboard);
  }

  // ==================== LEVEL REWARDS LIST ====================

  const levelRewardsList = document.getElementById("level-rewards-list");
  if (levelRewardsList) {
    levelRewardsList.addEventListener("click", (e) => {
      const editBtn = e.target.closest(".edit-reward-btn");
      if (editBtn) {
        document.getElementById("reward-level").value = editBtn.dataset.level;
        document.getElementById("reward-role-select").value =
          editBtn.dataset.roleId;
        new bootstrap.Modal(
          document.getElementById("addLevelRewardModal")
        ).show();
      }

      const deleteBtn = e.target.closest(".delete-reward-btn");
      if (
        deleteBtn &&
        confirm(`Delete reward for Level ${deleteBtn.dataset.level}?`)
      ) {
        deleteLevelReward(deleteBtn.dataset.level);
      }
    });
  }

  // Reset level reward modal on close
  const levelRewardModal = document.getElementById("addLevelRewardModal");
  if (levelRewardModal) {
    levelRewardModal.addEventListener("hidden.bs.modal", () => {
      document.getElementById("level-reward-form").reset();
    });
  }

  // ==================== YOUTUBE TAB ====================

  const addYtBtn = document.getElementById("add-yt-notification-btn");
  if (addYtBtn) {
    addYtBtn.addEventListener("click", () => {
      const form = document.getElementById("yt-notification-form");
      form.reset();

      // Set default custom message (matches bot's default)
      document.getElementById("yt-custom-message").value =
        "🔔 {@role} **{channel_name}** has uploaded a new video!\n\n" +
        "**{video_title}**\n{video_url}";

      const statusEl = document.getElementById("yt-channel-finder-status");
      statusEl.innerHTML = 'Enter a @handle or channel URL and click "Find".';
      statusEl.className = "form-text";
      statusEl.dataset.channelId = "";
      statusEl.dataset.channelName = "";

      document.getElementById("yt-discord-channel-select").value = "";
      document.getElementById("yt-mention-role-select").value = "";

      new bootstrap.Modal(
        document.getElementById("addYtNotificationModal")
      ).show();
    });
  }

  const ytNotificationForm = document.getElementById("yt-notification-form");
  if (ytNotificationForm) {
    ytNotificationForm.addEventListener("submit", saveYtNotification);
  }

  // YouTube configs container (edit/delete buttons)
  const ytConfigsContainer = document.getElementById(
    "youtube-configs-container"
  );
  if (ytConfigsContainer) {
    ytConfigsContainer.addEventListener("click", (e) => {
      const editBtn = e.target.closest(".edit-yt-btn");
      if (editBtn) {
        const config = JSON.parse(editBtn.dataset.config);
        document.getElementById("yt-channel-input").value =
          config.yt_channel_name;

        const statusEl = document.getElementById("yt-channel-finder-status");
        statusEl.innerHTML = `✅ Found: <strong>${config.yt_channel_name}</strong> (ID: ${config.yt_channel_id})`;
        statusEl.dataset.channelId = config.yt_channel_id;
        statusEl.dataset.channelName = config.yt_channel_name;

        document.getElementById("yt-discord-channel-select").value =
          config.target_channel_id;
        document.getElementById("yt-mention-role-select").value =
          config.mention_role_id || "";
        document.getElementById("yt-custom-message").value =
          config.custom_message;

        new bootstrap.Modal(
          document.getElementById("addYtNotificationModal")
        ).show();
      }

      const deleteBtn = e.target.closest(".delete-yt-btn");
      if (deleteBtn) {
        deleteYtNotification(
          deleteBtn.dataset.ytChannelId,
          deleteBtn.dataset.ytChannelName
        );
      }
    });
  }

  // YouTube channel finder button
  const findYtBtn = document.getElementById("find-yt-channel-btn");
  if (findYtBtn) {
    findYtBtn.addEventListener("click", findYouTubeChannel);
  }

  // ==================== MAIN DASHBOARD REFRESH ====================

  const refreshBtn = document.getElementById("refresh-dashboard-btn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () {
      showToast("Refreshing all server data...", "info");

      const icon = refreshBtn.querySelector("i");
      if (icon) icon.classList.add("fa-spin");
      refreshBtn.disabled = true;

      loadDashboardData().finally(() => {
        setTimeout(() => {
          if (icon) icon.classList.remove("fa-spin");
          refreshBtn.disabled = false;
        }, 1000);
      });
    });
  }

  console.log("✅ All event listeners initialized");
}

// YouTube channel finder function (if not already defined)
async function findYouTubeChannel() {
  const btn = document.getElementById("find-yt-channel-btn");
  const input = document.getElementById("yt-channel-input");
  const statusEl = document.getElementById("yt-channel-finder-status");
  const query = input.value.trim();

  if (!query) {
    statusEl.textContent = "Please enter a channel @handle or URL.";
    statusEl.className = "form-text text-danger";
    return;
  }

  const originalBtnHTML = btn.innerHTML;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Finding...';
  btn.disabled = true;
  statusEl.textContent = "Searching...";
  statusEl.className = "form-text text-muted";
  statusEl.dataset.channelId = "";
  statusEl.dataset.channelName = "";

  try {
    const response = await fetch(`/api/youtube/find-channel?query=${encodeURIComponent(query)}`);
    const data = await response.json();
    
    if (!response.ok) {
      throw new Error(data.error || "Failed to find channel.");
    }

    statusEl.innerHTML = `✅ Found: <strong>${data.channel_name}</strong> (ID: ${data.channel_id})`;
    statusEl.className = "form-text text-success";
    statusEl.dataset.channelId = data.channel_id;
    statusEl.dataset.channelName = data.channel_name;
    input.value = data.channel_name;
    
  } catch (error) {
    statusEl.textContent = `❌ Error: ${error.message}`;
    statusEl.className = "form-text text-danger";
  } finally {
    btn.innerHTML = originalBtnHTML;
    btn.disabled = false;
  }
}

// ==================== OTHER API FUNCTIONS ====================

async function loadLeaderboard() {
  const limit = document.getElementById("leaderboard-limit").value;
  const search = document.getElementById("leaderboard-search").value;
  const body = document.getElementById("leaderboard-body");
  body.innerHTML =
    '<tr><td colspan="4" class="text-center py-4"><div class="spinner-border spinner-border-sm"></div></td></tr>';

  try {
    const response = await fetch(
      `/api/server/${GUILD_ID}/leaderboard?limit=${limit}&search=${search}`
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    if (data.length === 0) {
      body.innerHTML =
        '<tr><td colspan="4" class="text-center text-muted py-4">No users found.</td></tr>';
      return;
    }
    body.innerHTML = data
      .map(
        (user, index) => `
            <tr>
                <td>${index + 1}</td>
                <td>${user.username}</td>
                <td>${user.level}</td>
                <td>${user.xp.toLocaleString()}</td>
            </tr>
        `
      )
      .join("");
  } catch (error) {
    body.innerHTML = `<tr><td colspan="4" class="text-center text-danger py-4">Error loading leaderboard.</td></tr>`;
    showToast(error.message, "danger");
  }
}

async function saveGeneralSettings(event) {
  event.preventDefault();
  const btn = document.getElementById("save-general-settings-btn");
  btn.disabled = true;
  btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Saving...`;
  const data = {
    xp_per_message: document.getElementById("xp_per_message").value,
    xp_per_image: document.getElementById("xp_per_image").value,
    xp_per_minute_in_voice: document.getElementById("xp_per_minute_in_voice")
      .value,
    voice_xp_limit: document.getElementById("voice_xp_limit").value,
  };
  try {
    const response = await fetch(`/api/server/${GUILD_ID}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    showToast("General settings saved successfully!", "success");
  } catch (error) {
    showToast(`Error: ${error.message}`, "danger");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i class="fas fa-save me-2"></i>Save Settings`;
  }
}

async function saveTimeChannels(event) {
  event.preventDefault();
  const btn = document.getElementById("save-time-channels-btn");
  btn.disabled = true;
  btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Saving...`;
  const data = {
    is_enabled: document.getElementById("time-channels-enabled").checked,
    date_channel_id: document.getElementById("date-channel-select").value,
    india_channel_id: document.getElementById("india-channel-select").value,
    japan_channel_id: document.getElementById("japan-channel-select").value,
  };
  try {
    const response = await fetch(`/api/server/${GUILD_ID}/time-channels`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    showToast("Time channel settings saved!", "success");
  } catch (error) {
    showToast(`Error: ${error.message}`, "danger");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i class="fas fa-save me-2"></i>Save Changes`;
  }
}

async function saveLevelNotifyChannel() {
  const btn = document.getElementById("save-notify-channel-btn");
  btn.disabled = true;
  const select = document.getElementById("level-notify-channel-select");
  const channelId = select.value;
  const channelName = select.options[select.selectedIndex].text;
  const data = channelId
    ? { channel_id: channelId, channel_name: channelName }
    : { channel_id: null, channel_name: null };

  try {
    const response = await fetch(
      `/api/server/${GUILD_ID}/level-notify-channel`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }
    );
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    showToast("Notification channel updated!", "success");
  } catch (error) {
    showToast(`Error: ${error.message}`, "danger");
  } finally {
    btn.disabled = false;
  }
}

async function saveLevelReward(event) {
  event.preventDefault();
  const form = event.target;
  const level = form.querySelector("#reward-level").value;
  const roleId = form.querySelector("#reward-role-select").value;
  const roleName = form.querySelector("#reward-role-select").options[
    form.querySelector("#reward-role-select").selectedIndex
  ].text;
  try {
    const response = await fetch(`/api/server/${GUILD_ID}/level-reward`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        level,
        role_id: roleId,
        role_name: roleName,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    showToast("Level reward saved!", "success");
    bootstrap.Modal.getInstance(
      document.getElementById("addLevelRewardModal")
    ).hide();
    loadDashboardData();
  } catch (error) {
    showToast(`Error saving reward: ${error.message}`, "danger");
  }
}

async function deleteLevelReward(level) {
  try {
    const response = await fetch(
      `/api/server/${GUILD_ID}/level-reward?level=${level}`,
      { method: "DELETE" }
    );
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    showToast(`Reward for level ${level} deleted.`, "success");
    loadDashboardData();
  } catch (error) {
    showToast(`Error deleting reward: ${error.message}`, "danger");
  }
}

// ==================== UTILITY FUNCTIONS ====================

function showLoader(loaderId, contentId) {
  const loader = document.getElementById(loaderId);
  const content = document.getElementById(contentId);
  if (loader) loader.style.display = "block";
  if (content) content.style.display = "none";
  if (content) content.classList.add("d-none");
}

function hideLoader(loaderId, contentId) {
  const loader = document.getElementById(loaderId);
  const content = document.getElementById(contentId);

  if (loader) {
    loader.style.display = "none";
  }

  if (content) {
    content.style.display = "block";
    content.classList.remove("d-none");
  }
}

function showToast(message, type = "success", duration = 5000) {
  let container = document.getElementById("toast-container-main");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container-main";
    Object.assign(container.style, {
      position: "fixed",
      top: "80px",
      right: "20px",
      zIndex: 9999,
      maxWidth: "400px",
    });
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `alert alert-${type} alert-dismissible fade show shadow-lg`;
  toast.role = "alert";
  toast.style.whiteSpace = "pre-line"; // Allow line breaks

  const icon =
    type === "success"
      ? "check-circle"
      : type === "warning"
      ? "exclamation-triangle"
      : "exclamation-circle";

  toast.innerHTML = `
    <i class="fas fa-${icon} me-2"></i> 
    ${message} 
    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    const alertInstance = bootstrap.Alert.getOrCreateInstance(toast);
    if (alertInstance) {
      alertInstance.close();
    }
  }, duration);
}
