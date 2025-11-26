// Theme Toggle
console.log("🎨 [Theme] Script file loaded");

(function () {
  "use strict";

  const THEME_KEY = "supporter-bot-theme";
  let initialized = false;

  // Get current theme
  function getCurrentTheme() {
    const savedTheme = localStorage.getItem(THEME_KEY);
    console.log("📋 [Theme] Saved theme from localStorage:", savedTheme);

    if (!savedTheme) {
      const prefersDark =
        window.matchMedia &&
        window.matchMedia("(prefers-color-scheme: dark)").matches;
      const systemTheme = prefersDark ? "dark" : "light";
      console.log(
        "💻 [Theme] No saved theme, using system preference:",
        systemTheme
      );
      return systemTheme;
    }

    return savedTheme;
  }

  // Set theme
  function setTheme(theme) {
    console.log("🎨 [Theme] Setting theme to:", theme);
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
    updateToggleButton(theme);
    console.log("✅ [Theme] Theme changed successfully to:", theme);
  }

  // Update toggle button icon
  function updateToggleButton(theme) {
    const icon = document.querySelector(".theme-toggle-slider i");
    if (icon) {
      const oldIcon = icon.className;
      icon.className = theme === "dark" ? "fas fa-moon" : "fas fa-sun";
      console.log(
        "🔄 [Theme] Icon updated from",
        oldIcon,
        "to",
        icon.className
      );
    } else {
      console.warn("⚠️ [Theme] Icon element not found");
    }
  }

  // Toggle theme
  function toggleTheme() {
    const currentTheme = getCurrentTheme();
    const newTheme = currentTheme === "light" ? "dark" : "light";
    console.log("🔄 [Theme] Toggling from", currentTheme, "to", newTheme);
    setTheme(newTheme);

    // Add pulse animation
    const btn = document.getElementById("themeToggle");
    if (btn) {
      btn.style.transform = "scale(0.95)";
      setTimeout(() => (btn.style.transform = "scale(1)"), 100);
    }
  }

  // Initialize
  function init() {
    if (initialized) {
      console.warn("⚠️ [Theme] Already initialized, skipping");
      return;
    }

    console.log("🚀 [Theme] Initializing...");

    const savedTheme = getCurrentTheme();
    setTheme(savedTheme);

    // Attach click event
    const themeToggle = document.getElementById("themeToggle");

    if (themeToggle) {
      console.log("✅ [Theme] Toggle button found, attaching listener");

      // Remove any existing listeners first
      const newElement = themeToggle.cloneNode(true);
      themeToggle.parentNode.replaceChild(newElement, themeToggle);

      // Attach new listener
      newElement.addEventListener("click", function (e) {
        console.log("🖱️ [Theme] Button clicked!");
        e.preventDefault();
        e.stopPropagation();
        toggleTheme();
      });

      // Also try with pointer events
      newElement.style.cursor = "pointer";
      newElement.style.userSelect = "none";

      console.log("✅ [Theme] Click listener attached successfully");
    } else {
      console.error(
        "❌ [Theme] Toggle button with ID 'themeToggle' NOT FOUND!"
      );
      console.log(
        "🔍 [Theme] Available elements with class theme-toggle-btn:",
        document.querySelectorAll(".theme-toggle-btn").length
      );
    }

    // Keyboard shortcut: Ctrl+Shift+D
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "D") {
        e.preventDefault();
        console.log("⌨️ [Theme] Keyboard shortcut triggered");
        toggleTheme();
      }
    });

    initialized = true;
    console.log("✅ [Theme] Initialization complete");
    console.log("💡 [Theme] Try clicking the toggle or pressing Ctrl+Shift+D");
  }

  // Run when DOM is ready - with multiple fallbacks
  if (document.readyState === "loading") {
    console.log("⏳ [Theme] DOM still loading, waiting...");
    document.addEventListener("DOMContentLoaded", init);
  } else {
    console.log("✅ [Theme] DOM already loaded, initializing now");
    init();
  }

  // Backup: Also try after a short delay
  setTimeout(function () {
    if (!initialized) {
      console.log("🔄 [Theme] Backup initialization triggered");
      init();
    }
  }, 500);

  console.log("🎨 [Theme] Script setup complete");
})();
