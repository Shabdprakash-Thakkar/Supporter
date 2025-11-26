document.addEventListener("DOMContentLoaded", () => {
  console.log("🔔 Reminders JS loaded");

  // 1. Load immediately (in case it's the active tab)
  loadReminders();

  // 2. Load when the refresh button is clicked
  const refreshBtn = document.getElementById("refreshRemindersBtn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      const icon = refreshBtn.querySelector("i");
      if (icon) icon.classList.add("fa-spin");
      loadReminders().finally(() => {
        if (icon) icon.classList.remove("fa-spin");
      });
    });
  }

  // 3. Load when the tab is clicked/shown
  const reminderTabBtn = document.getElementById("reminders-tab");
  if (reminderTabBtn) {
    reminderTabBtn.addEventListener("shown.bs.tab", function (event) {
      console.log("🔔 Reminders tab shown - fetching data...");
      loadReminders();
    });
  }
});

async function loadReminders() {
  // Check if we are on the server config page
  if (typeof GUILD_ID === "undefined") {
    console.error("❌ GUILD_ID is undefined - not on server config page");
    return;
  }

  const loader = document.getElementById("remindersLoader");
  const container = document.getElementById("remindersContainer");

  // If these elements don't exist (HTML issue), stop here
  if (!loader || !container) {
    console.error(
      "❌ Reminders HTML elements not found. Check reminders.html inclusion."
    );
    return;
  }

  loader.classList.remove("d-none");
  container.classList.add("d-none");

  console.log(`fetching /api/server/${GUILD_ID}/reminders`);

  try {
    const response = await fetch(`/api/server/${GUILD_ID}/reminders`);
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Failed to load reminders");
    }

    console.log("✅ Reminders data received:", data);

    // Check if data has reminders array
    if (!data.reminders || !Array.isArray(data.reminders)) {
      console.error("❌ Invalid data structure:", data);
      throw new Error("Invalid response format");
    }

    renderReminders(data.reminders);
  } catch (error) {
    console.error("Error loading reminders:", error);
    container.innerHTML = `
      <div class="alert alert-danger">
        <i class="fas fa-exclamation-triangle me-2"></i>
        Error loading reminders: ${escapeHtml(error.message)}
        <br><small>Check console for details</small>
      </div>
    `;
  } finally {
    loader.classList.add("d-none");
    container.classList.remove("d-none");
  }
}

// Flask_Frontend/static/js/reminders.js

// ... (keep the event listeners at the top the same) ...

function renderReminders(reminders) {
  const container = document.getElementById("remindersContainer");

  if (!reminders || reminders.length === 0) {
    container.innerHTML = `
      <div class="text-center text-muted py-5">
        <i class="fas fa-inbox fa-3x mb-3 d-block opacity-50"></i>
        <p class="mb-0">No active reminders found.</p>
        <small>Use <code>/r1-create</code> in Discord to create one.</small>
      </div>
    `;
    return;
  }

  container.innerHTML = reminders
    .map((reminder) => {
      const nextRun = new Date(reminder.next_run);

      // Check statuses
      const isPaused = reminder.status === "paused";
      const isCompleted = reminder.status === "completed";

      // Determine Badge
      let statusBadge = "";
      if (isPaused) {
        statusBadge = '<span class="badge bg-warning text-dark">Paused</span>';
      } else if (isCompleted) {
        statusBadge =
          '<span class="badge bg-success"><i class="fas fa-check me-1"></i>Completed</span>';
      } else {
        statusBadge = '<span class="badge bg-primary">Active</span>';
      }

      // Determine Card Class
      const cardClass = isCompleted
        ? "bg-light text-muted border-success"
        : isPaused
        ? "paused"
        : "";

      // Format the timezone display
      const timezoneDisplay = reminder.timezone || "Asia/Kolkata";

      return `
      <div class="reminder-card card mb-3 shadow-sm ${cardClass}">
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-start flex-wrap">
            <div class="flex-grow-1 mb-3 mb-md-0">
              <h5 class="card-title mb-2 d-flex align-items-center gap-2">
                ${statusBadge}
                <small class="text-muted" style="font-size: 0.8em;">${escapeHtml(
                  reminder.reminder_id
                )}</small>
              </h5>
              
              <div class="mb-3 p-2 rounded border ${
                isCompleted ? "bg-white" : "bg-light"
              }">
                ${escapeHtml(reminder.message)}
              </div>
              
              <div class="row g-2 small text-muted">
                <div class="col-md-6">
                  <i class="fas fa-hashtag me-1"></i>
                  <strong>Channel:</strong> <span class="discord-channel" data-id="${
                    reminder.channel_id
                  }">Loading...</span>
                </div>
                ${
                  reminder.role_id
                    ? `
                <div class="col-md-6">
                  <i class="fas fa-at me-1"></i>
                  <strong>Role:</strong> <span class="discord-role" data-id="${reminder.role_id}">Loading...</span>
                </div>`
                    : ""
                }
                <div class="col-md-6">
                  <i class="fas fa-clock me-1"></i>
                  <strong>Next Run:</strong> ${nextRun.toLocaleString("en-IN", {
                    timeZone: timezoneDisplay,
                  })}
                </div>
                <div class="col-md-6">
                  <i class="fas fa-sync me-1"></i>
                  <strong>Interval:</strong> ${escapeHtml(reminder.interval)}
                </div>
                <div class="col-md-6">
                  <i class="fas fa-globe me-1"></i>
                  <strong>Timezone:</strong> ${escapeHtml(timezoneDisplay)}
                </div>
                <div class="col-md-6">
                  <i class="fas fa-history me-1"></i>
                  <strong>Runs:</strong> ${reminder.run_count || 0} times
                </div>
              </div>
            </div>
            
            <div class="d-flex flex-column gap-2 ms-md-3">
              ${
                !isCompleted
                  ? `
              <button class="btn btn-sm btn-outline-${
                isPaused ? "success" : "warning"
              }" 
                      onclick="toggleReminder('${reminder.reminder_id}', '${
                      reminder.status
                    }')">
                <i class="fas fa-${isPaused ? "play" : "pause"} me-1"></i>
                ${isPaused ? "Resume" : "Pause"}
              </button>
              `
                  : ""
              }
              
              <button class="btn btn-sm btn-outline-danger" 
                      onclick="deleteReminder('${reminder.reminder_id}')">
                <i class="fas fa-trash me-1"></i>Delete
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
    })
    .join("");

  // Load Discord metadata after rendering
  loadDiscordDataForReminders();
}

// ... (keep the rest of the functions the same) ...

async function loadDiscordDataForReminders() {
  try {
    // Re-use the existing discord data API
    const response = await fetch(`/api/server/${GUILD_ID}/discord-data`);
    const data = await response.json();

    if (!response.ok) return;

    // Fill Channels
    document.querySelectorAll(".discord-channel").forEach((el) => {
      const ch = data.channels.find((c) => c.id === el.dataset.id);
      if (ch) el.textContent = "#" + ch.name;
      else el.textContent = "Unknown/Deleted";
    });

    // Fill Roles
    document.querySelectorAll(".discord-role").forEach((el) => {
      const r = data.roles.find((role) => role.id === el.dataset.id);
      if (r) el.textContent = "@" + r.name;
      else el.textContent = "Unknown Role";
    });
  } catch (e) {
    console.error("Failed to load discord metadata", e);
  }
}

async function toggleReminder(reminderId, currentStatus) {
  if (
    !confirm(
      `Are you sure you want to ${
        currentStatus === "active" ? "pause" : "resume"
      } this reminder?`
    )
  )
    return;

  try {
    await fetch(`/api/server/${GUILD_ID}/reminders/${reminderId}/toggle`, {
      method: "POST",
    });
    showToast(
      `Reminder ${currentStatus === "active" ? "paused" : "resumed"}`,
      "success"
    );
    loadReminders();
  } catch (error) {
    showToast("Error toggling reminder", "danger");
  }
}

async function deleteReminder(reminderId) {
  if (!confirm(`Delete reminder ${reminderId}?`)) return;

  try {
    await fetch(`/api/server/${GUILD_ID}/reminders/${reminderId}`, {
      method: "DELETE",
    });
    showToast("Reminder deleted", "success");
    loadReminders();
  } catch (error) {
    showToast("Error deleting reminder", "danger");
  }
}

function escapeHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
