

// ==================== CONSTANTS ====================

// Content type flags
const CONTENT_TYPES = {
  PLAIN_TEXT: { value: 1, label: 'Plain Text', icon: 'fa-font', description: 'Regular text messages' },
  DISCORD_INVITES: { value: 2, label: 'Discord Invites', icon: 'fa-link', description: 'discord.gg/... links' },
  IMAGE_LINKS: { value: 4, label: 'Image Links', icon: 'fa-image', description: 'URLs to images (.png, .jpg, .gif)' },
  REGULAR_LINKS: { value: 8, label: 'Regular Links', icon: 'fa-globe', description: 'Other HTTP(S) URLs' },
  IMAGE_ATTACHMENTS: { value: 16, label: 'Image Attachments', icon: 'fa-file-image', description: 'Uploaded image files' },
  FILE_ATTACHMENTS: { value: 32, label: 'File Attachments', icon: 'fa-file', description: 'Uploaded non-image files' },
  EMBEDS: { value: 64, label: 'Embeds', icon: 'fa-code', description: 'Rich embeds' }
};

// Legacy restriction types for backward compatibility
const LEGACY_RESTRICTION_TYPES = {
  block_invites: {
    label: 'Block Discord Invites',
    icon: 'fa-ban',
    color: 'warning',
    description: 'Block Discord invite links only',
    needsRedirect: false,
    allowed: 125,
    blocked: 2
  },
  block_all_links: {
    label: 'Block All Links',
    icon: 'fa-link-slash',
    color: 'danger',
    description: 'Block all types of links',
    needsRedirect: false,
    allowed: 49,
    blocked: 14
  },
  media_only: {
    label: 'Media Only',
    icon: 'fa-photo-video',
    color: 'info',
    description: 'Only media allowed, no text',
    needsRedirect: true,
    allowed: 124,
    blocked: 1
  },
  text_only: {
    label: 'Text Only',
    icon: 'fa-align-left',
    color: 'success',
    description: 'Only text and regular links allowed',
    needsRedirect: true,
    allowed: 9,
    blocked: 118
  }
};

// ==================== GLOBAL STATE ====================

let currentRestrictions = [];
let allChannels = [];
let allRoles = [];
let editingRestrictionId = null;
let restrictionModal = null;

// ==================== INITIALIZATION ====================

document.addEventListener('DOMContentLoaded', () => {
  console.log('✅ Channel Restrictions V2 DOM loaded');
  console.log('📍 GUILD_ID:', typeof GUILD_ID !== 'undefined' ? GUILD_ID : 'NOT DEFINED');

  // Initialize Bootstrap modal
  const modalElement = document.getElementById('restrictionModal');
  if (modalElement) {
    restrictionModal = new bootstrap.Modal(modalElement);
    console.log('✅ Modal initialized');
  } else {
    console.error('❌ Modal element not found!');
  }

  // Set up event listeners
  initializeEventListeners();

  // Load data
  if (typeof GUILD_ID !== 'undefined') {
    loadRestrictionsData();
  } else {
    console.error('❌ GUILD_ID is not defined!');
  }
});

function initializeEventListeners() {
  // Add Restriction Button
  const addBtn = document.getElementById('addRestrictionBtn');
  if (addBtn) {
    addBtn.addEventListener('click', function (e) {
      e.preventDefault();
      console.log('🖱️ Add Restriction button clicked');
      openAddModal();
    });
    console.log('✅ Add button listener attached');
  } else {
    console.error('❌ addRestrictionBtn not found!');
  }

  // Save Restriction Button
  const saveBtn = document.getElementById('saveRestrictionBtn');
  if (saveBtn) {
    saveBtn.addEventListener('click', function (e) {
      e.preventDefault();
      console.log('🖱️ Save Restriction button clicked');
      saveRestriction();
    });
    console.log('✅ Save button listener attached');
  } else {
    console.error('❌ saveRestrictionBtn not found!');
  }

  // Mode Change Handler
  const modeSelect = document.getElementById('restrictionMode');
  if (modeSelect) {
    modeSelect.addEventListener('change', handleModeChange);
    console.log('✅ Mode select listener attached');
  }
}

// ==================== DATA LOADING ====================

async function loadRestrictionsData() {
  showLoader();
  console.log('📡 Loading restrictions data for guild:', GUILD_ID);

  try {
    const [restrictionsResponse, discordResponse] = await Promise.all([
      fetch(`/api/server/${GUILD_ID}/channel-restrictions-v2/data`),
      fetch(`/api/server/${GUILD_ID}/discord-data`)
    ]);

    console.log('📡 Restrictions response status:', restrictionsResponse.status);
    console.log('📡 Discord data response status:', discordResponse.status);

    if (!restrictionsResponse.ok) {
      const errorText = await restrictionsResponse.text();
      console.error('❌ Restrictions API error:', errorText);
      throw new Error(`Failed to load restrictions: ${restrictionsResponse.status}`);
    }

    if (!discordResponse.ok) {
      const errorText = await discordResponse.text();
      console.error('❌ Discord API error:', errorText);
      throw new Error(`Failed to load Discord data: ${discordResponse.status}`);
    }

    const restrictionsData = await restrictionsResponse.json();
    const discordData = await discordResponse.json();

    currentRestrictions = (restrictionsData.restrictions || []).map(r => ({
      ...r,
      allowed_content_types: r.allowed_content_types || 0,
      blocked_content_types: r.blocked_content_types || 0
    }));

    allChannels = discordData.channels.filter(c => c.type === 0);
    allRoles = discordData.roles || [];

    console.log('✅ Loaded restrictions:', currentRestrictions.length);
    console.log('✅ Loaded channels:', allChannels.length);

    renderRestrictionsTable();

  } catch (error) {
    console.error('❌ Error loading restrictions:', error);
    showToast('Failed to load channel restrictions. Check console for details.', 'danger');

    const tbody = document.getElementById('restrictionsTableBody');
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" class="text-center text-danger py-5">
            <i class="fas fa-exclamation-triangle fa-3x mb-3 d-block"></i>
            <p class="mb-2"><strong>Failed to load restrictions</strong></p>
            <p class="small text-muted mb-3">${escapeHtml(error.message)}</p>
            <button class="btn btn-sm btn-outline-primary" onclick="loadRestrictionsData()">
              <i class="fas fa-sync me-2"></i>Retry
            </button>
          </td>
        </tr>
      `;
    }
  } finally {
    hideLoader();
  }
}

// ==================== RENDERING ====================

function renderRestrictionsTable() {
  const tbody = document.getElementById('restrictionsTableBody');
  if (!tbody) {
    console.error('❌ restrictionsTableBody not found!');
    return;
  }

  if (currentRestrictions.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="text-center text-muted py-5">
          <i class="fas fa-inbox fa-3x mb-3 d-block"></i>
          <p class="mb-0">No channel restrictions configured yet.</p>
          <button class="btn btn-primary btn-sm mt-3" onclick="openAddModal()">
            <i class="fas fa-plus me-1"></i> Add First Restriction
          </button>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = currentRestrictions.map(restriction => {
    const allowedTypes = getContentTypeNames(restriction.allowed_content_types || 0);
    const blockedTypes = getContentTypeNames(restriction.blocked_content_types || 0);

    return `
      <tr>
        <td>
          <i class="fas fa-hashtag text-muted me-2"></i>
          <strong>${escapeHtml(restriction.channel_name)}</strong>
        </td>
        <td>
          ${renderContentTypeBadges(allowedTypes, 'success')}
        </td>
        <td>
          ${renderContentTypeBadges(blockedTypes, 'danger')}
        </td>
        <td>
          ${restriction.redirect_channel_name ?
        `<i class="fas fa-arrow-right text-muted me-2"></i>${escapeHtml(restriction.redirect_channel_name)}` :
        '<span class="text-muted">—</span>'}
        </td>
        <td class="text-end">
          <button class="btn btn-sm btn-outline-primary me-1" onclick="editRestriction(${restriction.id})">
            <i class="fas fa-edit"></i>
          </button>
          <button class="btn btn-sm btn-outline-danger" onclick="deleteRestriction(${restriction.id}, '${escapeHtml(restriction.channel_name).replace(/'/g, "\\'")}')">
            <i class="fas fa-trash"></i>
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

function renderContentTypeBadges(types, variant) {
  if (!types || types.length === 0) {
    return '<span class="badge bg-secondary">None</span>';
  }

  return types.map(type => {
    const contentType = Object.values(CONTENT_TYPES).find(ct =>
      ct.label.toLowerCase() === type.toLowerCase()
    );
    const icon = contentType ? contentType.icon : 'fa-question';
    return `<span class="badge bg-${variant} me-1 mb-1"><i class="fas ${icon} me-1"></i>${type}</span>`;
  }).join(' ');
}

function getContentTypeNames(flags) {
  const names = [];
  for (const [key, value] of Object.entries(CONTENT_TYPES)) {
    if (flags & value.value) {
      names.push(value.label);
    }
  }
  return names;
}

// ==================== MODAL MANAGEMENT ====================

function openAddModal() {
  console.log('📂 Opening add modal...');

  editingRestrictionId = null;

  const modalTitle = document.getElementById('modalTitle');
  const saveBtn = document.getElementById('saveRestrictionBtn');

  if (modalTitle) modalTitle.textContent = 'Add Channel Restriction';
  if (saveBtn) saveBtn.innerHTML = '<i class="fas fa-plus me-2"></i>Add Restriction';

  // Reset form
  const form = document.getElementById('restrictionForm');
  if (form) form.reset();

  const modeSelect = document.getElementById('restrictionMode');
  if (modeSelect) modeSelect.value = 'granular';

  handleModeChange();
  populateChannelDropdown();

  // Show modal
  if (restrictionModal) {
    restrictionModal.show();
    console.log('✅ Modal shown');
  } else {
    console.error('❌ Modal not initialized, trying to create new instance');
    const modalElement = document.getElementById('restrictionModal');
    if (modalElement) {
      restrictionModal = new bootstrap.Modal(modalElement);
      restrictionModal.show();
    } else {
      console.error('❌ Cannot find modal element!');
      showToast('Error: Could not open modal', 'danger');
    }
  }
}

function editRestriction(restrictionId) {
  console.log('📝 Editing restriction:', restrictionId);

  const restriction = currentRestrictions.find(r => r.id === restrictionId);
  if (!restriction) {
    showToast('Restriction not found', 'danger');
    return;
  }

  editingRestrictionId = restrictionId;

  const modalTitle = document.getElementById('modalTitle');
  const saveBtn = document.getElementById('saveRestrictionBtn');

  if (modalTitle) modalTitle.textContent = 'Edit Channel Restriction';
  if (saveBtn) saveBtn.innerHTML = '<i class="fas fa-save me-2"></i>Save Changes';

  populateChannelDropdown();

  // Set form values after populating dropdowns
  setTimeout(() => {
    const channelSelect = document.getElementById('channelSelect');
    const redirectSelect = document.getElementById('redirectChannelSelect');

    if (channelSelect) channelSelect.value = restriction.channel_id;
    if (redirectSelect) redirectSelect.value = restriction.redirect_channel_id || '';

    const isLegacy = restriction.restriction_type && LEGACY_RESTRICTION_TYPES[restriction.restriction_type];

    const modeSelect = document.getElementById('restrictionMode');
    if (isLegacy && modeSelect) {
      modeSelect.value = 'legacy';
      const legacyTypeSelect = document.getElementById('legacyTypeSelect');
      if (legacyTypeSelect) legacyTypeSelect.value = restriction.restriction_type;
    } else if (modeSelect) {
      modeSelect.value = 'granular';
    }

    handleModeChange();

    if (!isLegacy) {
      setContentTypeCheckboxes('allowed', restriction.allowed_content_types || 0);
      setContentTypeCheckboxes('blocked', restriction.blocked_content_types || 0);
    }
  }, 100);

  if (restrictionModal) {
    restrictionModal.show();
  }
}

function handleModeChange() {
  const modeSelect = document.getElementById('restrictionMode');
  const mode = modeSelect ? modeSelect.value : 'granular';

  const legacySection = document.getElementById('legacyModeSection');
  const granularSection = document.getElementById('granularModeSection');

  if (mode === 'legacy') {
    if (legacySection) legacySection.style.display = 'block';
    if (granularSection) granularSection.style.display = 'none';
  } else {
    if (legacySection) legacySection.style.display = 'none';
    if (granularSection) granularSection.style.display = 'block';
    renderContentTypeCheckboxes();
  }
}

function renderContentTypeCheckboxes() {
  const allowedContainer = document.getElementById('allowedContentTypes');
  const blockedContainer = document.getElementById('blockedContentTypes');

  if (!allowedContainer || !blockedContainer) {
    console.error('❌ Content type containers not found');
    return;
  }

  const checkboxHTML = (key, type, category) => `
    <div class="form-check mb-2">
      <input class="form-check-input" type="checkbox" 
             id="${category}_${key}" 
             value="${type.value}"
             onchange="handleContentTypeChange('${category}', '${key}')">
      <label class="form-check-label" for="${category}_${key}">
        <i class="fas ${type.icon} me-2"></i>
        <strong>${type.label}</strong>
        <small class="text-muted d-block">${type.description}</small>
      </label>
    </div>
  `;

  allowedContainer.innerHTML = Object.entries(CONTENT_TYPES)
    .map(([key, type]) => checkboxHTML(key, type, 'allowed'))
    .join('');

  blockedContainer.innerHTML = Object.entries(CONTENT_TYPES)
    .map(([key, type]) => checkboxHTML(key, type, 'blocked'))
    .join('');
}

function handleContentTypeChange(category, key) {
  const checkbox = document.getElementById(`${category}_${key}`);
  const oppositeCategory = category === 'allowed' ? 'blocked' : 'allowed';
  const oppositeCheckbox = document.getElementById(`${oppositeCategory}_${key}`);

  if (checkbox && checkbox.checked && oppositeCheckbox && oppositeCheckbox.checked) {
    oppositeCheckbox.checked = false;
  }
}

function setContentTypeCheckboxes(category, flags) {
  for (const [key, type] of Object.entries(CONTENT_TYPES)) {
    const checkbox = document.getElementById(`${category}_${key}`);
    if (checkbox) {
      checkbox.checked = (flags & type.value) > 0;
    }
  }
}

function getContentTypeFlags(category) {
  let flags = 0;
  for (const [key, type] of Object.entries(CONTENT_TYPES)) {
    const checkbox = document.getElementById(`${category}_${key}`);
    if (checkbox && checkbox.checked) {
      flags |= type.value;
    }
  }
  return flags;
}

function populateChannelDropdown() {
  const channelSelect = document.getElementById('channelSelect');
  const redirectSelect = document.getElementById('redirectChannelSelect');

  if (!channelSelect || !redirectSelect) {
    console.error('❌ Channel select elements not found');
    return;
  }

  const restrictedChannelIds = currentRestrictions.map(r => r.channel_id);

  const availableChannels = editingRestrictionId
    ? allChannels
    : allChannels.filter(c => !restrictedChannelIds.includes(c.id));

  channelSelect.innerHTML = `
    <option value="">-- Select a channel --</option>
    ${availableChannels.map(channel => `
      <option value="${channel.id}"># ${escapeHtml(channel.name)}</option>
    `).join('')}
  `;

  redirectSelect.innerHTML = `
    <option value="">No redirect</option>
    ${allChannels.map(channel => `
      <option value="${channel.id}"># ${escapeHtml(channel.name)}</option>
    `).join('')}
  `;

  console.log('✅ Channel dropdowns populated with', availableChannels.length, 'channels');
}

// ==================== SAVE RESTRICTION ====================

async function saveRestriction() {
  console.log('💾 Saving restriction...');

  const channelSelect = document.getElementById('channelSelect');
  const channelId = channelSelect ? channelSelect.value : '';
  const modeSelect = document.getElementById('restrictionMode');
  const mode = modeSelect ? modeSelect.value : 'granular';
  const redirectSelect = document.getElementById('redirectChannelSelect');
  const redirectChannelId = redirectSelect ? redirectSelect.value : '';

  if (!channelId) {
    showToast('Please select a channel', 'warning');
    return;
  }

  const channel = allChannels.find(c => c.id === channelId);
  const redirectChannel = redirectChannelId ? allChannels.find(c => c.id === redirectChannelId) : null;

  let payload = {
    channel_id: channelId,
    channel_name: channel ? channel.name : 'Unknown',
    redirect_channel_id: redirectChannelId || null,
    redirect_channel_name: redirectChannel ? redirectChannel.name : null
  };

  if (mode === 'legacy') {
    const legacyTypeSelect = document.getElementById('legacyTypeSelect');
    const legacyType = legacyTypeSelect ? legacyTypeSelect.value : 'block_invites';
    const legacyConfig = LEGACY_RESTRICTION_TYPES[legacyType];

    payload.restriction_type = legacyType;
    payload.allowed_content_types = legacyConfig.allowed;
    payload.blocked_content_types = legacyConfig.blocked;
  } else {
    const allowedFlags = getContentTypeFlags('allowed');
    const blockedFlags = getContentTypeFlags('blocked');

    if (allowedFlags === 0 && blockedFlags === 0) {
      showToast('Please select at least one content type to allow or block', 'warning');
      return;
    }

    if ((allowedFlags & blockedFlags) !== 0) {
      showToast('Cannot allow and block the same content types', 'danger');
      return;
    }

    payload.restriction_type = 'block_invites';
    payload.allowed_content_types = allowedFlags;
    payload.blocked_content_types = blockedFlags;
  }

  console.log('📤 Sending payload:', payload);

  try {
    showLoader();

    const url = editingRestrictionId
      ? `/api/server/${GUILD_ID}/channel-restrictions-v2/${editingRestrictionId}`
      : `/api/server/${GUILD_ID}/channel-restrictions-v2`;

    const method = editingRestrictionId ? 'PUT' : 'POST';

    const response = await fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await response.json();
    console.log('📥 Response:', data);

    if (response.ok) {
      showToast(data.message || 'Restriction saved successfully!', 'success');
      if (restrictionModal) restrictionModal.hide();
      await loadRestrictionsData();
    } else {
      showToast(data.error || 'Failed to save restriction', 'danger');
    }
  } catch (error) {
    console.error('❌ Error saving restriction:', error);
    showToast('An error occurred while saving', 'danger');
  } finally {
    hideLoader();
  }
}

// ==================== DELETE RESTRICTION ====================

async function deleteRestriction(restrictionId, channelName) {
  if (!confirm(`Are you sure you want to remove the restriction from #${channelName}?`)) {
    return;
  }

  console.log('🗑️ Deleting restriction:', restrictionId);

  try {
    showLoader();

    const response = await fetch(
      `/api/server/${GUILD_ID}/channel-restrictions-v2/${restrictionId}`,
      { method: 'DELETE' }
    );

    const data = await response.json();

    if (response.ok) {
      showToast(data.message || 'Restriction deleted successfully!', 'success');
      await loadRestrictionsData();
    } else {
      showToast(data.error || 'Failed to delete restriction', 'danger');
    }
  } catch (error) {
    console.error('❌ Error deleting restriction:', error);
    showToast('An error occurred while deleting', 'danger');
  } finally {
    hideLoader();
  }
}

// ==================== UTILITY FUNCTIONS ====================

function showLoader() {
  const overlay = document.getElementById('loadingOverlay');
  if (overlay) overlay.classList.remove('d-none');
}

function hideLoader() {
  const overlay = document.getElementById('loadingOverlay');
  if (overlay) overlay.classList.add('d-none');
}

function showToast(message, type = 'info') {
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container position-fixed top-0 end-0 p-3';
    container.style.zIndex = '9999';
    document.body.appendChild(container);
  }

  const toastHTML = `
    <div class="toast align-items-center text-white bg-${type} border-0" role="alert">
      <div class="d-flex">
        <div class="toast-body">${escapeHtml(message)}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
      </div>
    </div>
  `;

  container.insertAdjacentHTML('beforeend', toastHTML);

  const toastElement = container.lastElementChild;
  const toast = new bootstrap.Toast(toastElement, { delay: 4000 });
  toast.show();

  toastElement.addEventListener('hidden.bs.toast', () => toastElement.remove());
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Make functions available globally for onclick handlers
window.openAddModal = openAddModal;
window.editRestriction = editRestriction;
window.deleteRestriction = deleteRestriction;
window.handleContentTypeChange = handleContentTypeChange;
window.loadRestrictionsData = loadRestrictionsData;