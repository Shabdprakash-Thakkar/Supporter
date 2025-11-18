// ==================== DASHBOARD JAVASCRIPT V2.2 ====================

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

  try {
    const [config, discordData] = await Promise.all([
      fetch(`/api/server/${GUILD_ID}/config`).then((res) => res.json()),
      fetch(`/api/server/${GUILD_ID}/discord-data`).then((res) => res.json()),
    ]);

    if (config.error || discordData.error) {
      throw new Error(config.error || discordData.error);
    }

    // Populate all sections
    populateGeneralSettings(config.guild_settings);
    populateLevelingTab(config, discordData);
    populateTimeChannels(config.time_channel_config, discordData.channels);
    populateRewardModal(discordData.roles);

    // Initial load for the leaderboard
    loadLeaderboard();
  } catch (error) {
    console.error("❌ Fatal error loading dashboard data:", error);
    showToast("Error loading dashboard data. Please refresh.", "danger");
  } finally {
    hideLoader("general-settings-loader", "general-settings-content");
    hideLoader("time-channels-loader", "time-channels-content");
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

  // Populate Rewards List
  const rewardsContainer = document.getElementById("level-rewards-list");
  if (!level_rewards || level_rewards.length === 0) {
    rewardsContainer.innerHTML = `<div class="text-center text-muted py-4">No level rewards configured.</div>`;
  } else {
    const roleMap = new Map(roles.map((r) => [r.id, r.name]));
    rewardsContainer.innerHTML = level_rewards
      .map(
        (reward) => `
            <div class="reward-item p-3 mb-2 rounded-3 d-flex justify-content-between align-items-center">
                <div><strong>Level ${
                  reward.level
                }</strong> &rarr; <span class="badge bg-primary">${
          roleMap.get(reward.role_id) || reward.role_name || "Unknown Role"
        }</span></div>
                <div>
                    <button class="btn btn-sm btn-outline-secondary me-2 edit-reward-btn" data-level="${
                      reward.level
                    }" data-role-id="${
          reward.role_id
        }" title="Edit"><i class="fas fa-pencil-alt"></i></button>
                    <button class="btn btn-sm btn-outline-danger delete-reward-btn" data-level="${
                      reward.level
                    }" title="Delete"><i class="fas fa-trash"></i></button>
                </div>
            </div>`
      )
      .join("");
  }

  // Populate Notification Channel Dropdown
  const notifySelect = document.getElementById("level-notify-channel-select");
  const textChannels = channels.filter((c) => c.type === 0);
  notifySelect.innerHTML =
    '<option value="">-- Disable Notifications --</option>' +
    textChannels
      .map(
        (c) =>
          `<option value="${c.id}" ${
            level_notify_channel_id === c.id ? "selected" : ""
          }>#${c.name}</option>`
      )
      .join("");
  hideLoader("level-notify-channel-loader", "level-notify-channel-content");
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

// ==================== EVENT LISTENERS ====================

function initializeEventListeners() {
  document
    .getElementById("general-settings-form")
    .addEventListener("submit", saveGeneralSettings);
  document
    .getElementById("time-channels-form")
    .addEventListener("submit", saveTimeChannels);
  document
    .getElementById("level-reward-form")
    .addEventListener("submit", saveLevelReward);
  document
    .getElementById("save-notify-channel-btn")
    .addEventListener("click", saveLevelNotifyChannel);

  // Leaderboard search and limit listeners
  let debounceTimer;
  document
    .getElementById("leaderboard-search")
    .addEventListener("input", () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(loadLeaderboard, 300);
    });
  document
    .getElementById("leaderboard-limit")
    .addEventListener("change", loadLeaderboard);

  // Event delegation for reward buttons
  document
    .getElementById("level-rewards-list")
    .addEventListener("click", function (e) {
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

  // Reset modal form when closed
  document
    .getElementById("addLevelRewardModal")
    .addEventListener("hidden.bs.modal", () =>
      document.getElementById("level-reward-form").reset()
    );
}

// ==================== API FUNCTIONS ====================

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
  const originalText = btn.innerHTML;
  btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Saving...`;
  btn.disabled = true;
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
    btn.innerHTML = originalText;
    btn.disabled = false;
  }
}

async function saveTimeChannels(event) {
  event.preventDefault();
  const btn = document.getElementById("save-time-channels-btn");
  const originalText = btn.innerHTML;
  btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Saving...`;
  btn.disabled = true;
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
    btn.innerHTML = originalText;
    btn.disabled = false;
  }
}

async function saveLevelNotifyChannel() {
  const btn = document.getElementById("save-notify-channel-btn");
  btn.disabled = true;
  const select = document.getElementById("level-notify-channel-select");
  const channelId = select.value;
  const channelName = select.selectedOptions[0].text;

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
  const roleName = form.querySelector("#reward-role-select").selectedOptions[0]
    .text;
  try {
    const response = await fetch(`/api/server/${GUILD_ID}/level-reward`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        level,
        role_id: roleId,
        role_name: roleName,
        guild_name: "{{server.name}}",
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
  document.getElementById(loaderId).classList.remove("d-none");
  document.getElementById(contentId).classList.add("d-none");
}

function hideLoader(loaderId, contentId) {
  document.getElementById(loaderId).classList.add("d-none");
  document.getElementById(contentId).classList.remove("d-none");
}

function showToast(message, type = "success") {
  let container = document.getElementById("toast-container-main");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container-main";
    Object.assign(container.style, {
      position: "fixed",
      top: "80px",
      right: "20px",
      zIndex: 9999,
    });
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = `alert alert-${type} alert-dismissible fade show shadow-lg`;
  toast.role = "alert";
  const icon = type === "success" ? "check-circle" : "exclamation-triangle";
  toast.innerHTML = `<i class="fas fa-${icon} me-2"></i> ${message} <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
  container.appendChild(toast);
  setTimeout(() => bootstrap.Alert.getOrCreateInstance(toast)?.close(), 5000);
}
