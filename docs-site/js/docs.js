(() => {
  "use strict";

  /* ── Theme ─────────────────────────────────────────────────────────── */
  const root = document.documentElement;
  const saved = localStorage.getItem("nc-theme");
  if (saved) root.setAttribute("data-theme", saved);

  const themeBtn = document.querySelector(".theme-toggle");
  if (themeBtn) {
    const sunSVG = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;
    const moonSVG = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;

    const isDark = () => root.getAttribute("data-theme") !== "light" && !(root.getAttribute("data-theme") === null && window.matchMedia("(prefers-color-scheme: light)").matches);

    const updateIcon = () => { themeBtn.innerHTML = isDark() ? sunSVG : moonSVG; };
    updateIcon();

    themeBtn.addEventListener("click", () => {
      const next = isDark() ? "light" : "dark";
      root.setAttribute("data-theme", next);
      localStorage.setItem("nc-theme", next);
      updateIcon();
    });
  }

  /* ── Mobile sidebar ────────────────────────────────────────────────── */
  const sidebar  = document.querySelector(".sidebar");
  const overlay  = document.querySelector(".sidebar-overlay");
  const menuBtn  = document.querySelector(".mobile-menu-btn");

  const closeSidebar = () => {
    sidebar && sidebar.classList.remove("open");
    overlay && overlay.classList.remove("active");
  };
  const openSidebar = () => {
    sidebar && sidebar.classList.add("open");
    overlay && overlay.classList.add("active");
  };

  menuBtn  && menuBtn.addEventListener("click", openSidebar);
  overlay  && overlay.addEventListener("click", closeSidebar);

  /* ── TOC scroll-spy ────────────────────────────────────────────────── */
  const tocLinks = Array.from(document.querySelectorAll(".page-toc a"));
  if (tocLinks.length) {
    const headings = tocLinks.map(a => document.getElementById(a.getAttribute("href").replace("#", ""))).filter(Boolean);
    const onScroll = () => {
      const scrollY = window.scrollY + 90;
      let active = headings[0];
      for (const h of headings) {
        if (h.getBoundingClientRect().top + window.scrollY <= scrollY) active = h;
      }
      tocLinks.forEach(a => a.classList.toggle("active", a.getAttribute("href") === "#" + (active && active.id)));
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* ── Copy buttons ──────────────────────────────────────────────────── */
  document.querySelectorAll(".copy-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const pre = btn.closest(".code-header").nextElementSibling;
      const text = pre ? pre.innerText : "";
      navigator.clipboard.writeText(text).then(() => {
        btn.textContent = "Copied!";
        btn.classList.add("copied");
        setTimeout(() => { btn.textContent = "Copy"; btn.classList.remove("copied"); }, 2000);
      });
    });
  });

  /* ── Search ────────────────────────────────────────────────────────── */
  const INDEX = [
    // Getting Started
    { title: "Installation", section: "Getting Started", url: "docs/getting-started.html" },
    { title: "Quick Start — pip install neuralcleave", section: "Getting Started", url: "docs/getting-started.html#quickstart" },
    { title: "First Agent Setup", section: "Getting Started", url: "docs/getting-started.html#first-agent" },
    { title: "neuralcleave init", section: "Getting Started", url: "docs/getting-started.html#init" },
    // Architecture
    { title: "Architecture Overview", section: "Core Concepts", url: "docs/architecture.html" },
    { title: "Gateway (FastAPI + uvicorn)", section: "Architecture", url: "docs/architecture.html#gateway" },
    { title: "AgentRuntime → ModelRouter → ReflectionEngine", section: "Architecture", url: "docs/architecture.html#pipeline" },
    { title: "3-Tier Memory Pipeline", section: "Architecture", url: "docs/architecture.html#memory" },
    { title: "Plugin System (PEP 451 entry-points)", section: "Architecture", url: "docs/architecture.html#plugins" },
    // Memory
    { title: "Memory System", section: "Core Concepts", url: "docs/memory.html" },
    { title: "Redis — short-term memory", section: "Memory", url: "docs/memory.html#redis" },
    { title: "Qdrant — vector / semantic memory", section: "Memory", url: "docs/memory.html#qdrant" },
    { title: "SQLite — long-term memory", section: "Memory", url: "docs/memory.html#sqlite" },
    { title: "Session compaction", section: "Memory", url: "docs/memory.html#compaction" },
    { title: "Session archiver", section: "Memory", url: "docs/memory.html#archiver" },
    { title: "Per-node memory isolation (AgentOrchestrator)", section: "Memory", url: "docs/memory.html#orchestrator" },
    // LLM Providers
    { title: "LLM Providers", section: "LLM Routing", url: "docs/llm-providers.html" },
    { title: "Anthropic Claude", section: "LLM Providers", url: "docs/llm-providers.html#anthropic" },
    { title: "OpenAI GPT", section: "LLM Providers", url: "docs/llm-providers.html#openai" },
    { title: "Google Gemini", section: "LLM Providers", url: "docs/llm-providers.html#gemini" },
    { title: "DeepSeek", section: "LLM Providers", url: "docs/llm-providers.html#deepseek" },
    { title: "Ollama (local)", section: "LLM Providers", url: "docs/llm-providers.html#ollama" },
    { title: "Mistral AI", section: "LLM Providers", url: "docs/llm-providers.html#mistral" },
    { title: "xAI Grok", section: "LLM Providers", url: "docs/llm-providers.html#xai" },
    { title: "Cohere Command-R", section: "LLM Providers", url: "docs/llm-providers.html#cohere" },
    { title: "Moonshot / Kimi", section: "LLM Providers", url: "docs/llm-providers.html#moonshot" },
    { title: "Zhipu GLM", section: "LLM Providers", url: "docs/llm-providers.html#zhipu" },
    { title: "Alibaba Qwen / DashScope", section: "LLM Providers", url: "docs/llm-providers.html#qwen" },
    { title: "Baidu ERNIE", section: "LLM Providers", url: "docs/llm-providers.html#baidu" },
    { title: "ByteDance Doubao", section: "LLM Providers", url: "docs/llm-providers.html#bytedance" },
    { title: "Task-aware routing (10 task types)", section: "LLM Routing", url: "docs/llm-providers.html#routing" },
    { title: "Extended thinking (Anthropic)", section: "LLM Routing", url: "docs/llm-providers.html#thinking" },
    { title: "Privacy mode (Ollama-only)", section: "LLM Routing", url: "docs/llm-providers.html#privacy" },
    // Channels
    { title: "Channels Overview — 32 adapters", section: "Channels", url: "docs/channels.html" },
    { title: "Telegram", section: "Channels", url: "docs/channels.html#telegram" },
    { title: "Discord", section: "Channels", url: "docs/channels.html#discord" },
    { title: "Slack", section: "Channels", url: "docs/channels.html#slack" },
    { title: "WhatsApp", section: "Channels", url: "docs/channels.html#whatsapp" },
    { title: "Email (IMAP + SMTP)", section: "Channels", url: "docs/channels.html#email" },
    { title: "SMS / Twilio", section: "Channels", url: "docs/channels.html#sms" },
    { title: "Microsoft Teams", section: "Channels", url: "docs/channels.html#teams" },
    { title: "Google Chat", section: "Channels", url: "docs/channels.html#google-chat" },
    { title: "Slack Socket Mode", section: "Channels", url: "docs/channels.html#slack" },
    { title: "Matrix", section: "Channels", url: "docs/channels.html#matrix" },
    { title: "IRC", section: "Channels", url: "docs/channels.html#irc" },
    { title: "Signal (signal-cli)", section: "Channels", url: "docs/channels.html#signal" },
    { title: "Mattermost", section: "Channels", url: "docs/channels.html#mattermost" },
    { title: "Rocket.Chat", section: "Channels", url: "docs/channels.html#rocketchat" },
    { title: "Facebook Messenger", section: "Channels", url: "docs/channels.html#messenger" },
    { title: "Twitch IRC", section: "Channels", url: "docs/channels.html#twitch" },
    { title: "LINE", section: "Channels", url: "docs/channels.html#line" },
    { title: "Feishu / Lark", section: "Channels", url: "docs/channels.html#feishu" },
    { title: "Google Chat (service account)", section: "Channels", url: "docs/channels.html#google-chat" },
    { title: "iMessage (BlueBubbles)", section: "Channels", url: "docs/channels.html#imessage" },
    { title: "Synology Chat", section: "Channels", url: "docs/channels.html#synology" },
    { title: "Nostr (NIP-04)", section: "Channels", url: "docs/channels.html#nostr" },
    { title: "Twilio Voice (TwiML)", section: "Channels", url: "docs/channels.html#twilio-voice" },
    { title: "Zalo OA", section: "Channels", url: "docs/channels.html#zalo" },
    { title: "WeChat Work (WeCom)", section: "Channels", url: "docs/channels.html#wechat" },
    { title: "QQ Bot", section: "Channels", url: "docs/channels.html#qq" },
    { title: "Tlon / Urbit", section: "Channels", url: "docs/channels.html#tlon" },
    { title: "Mastodon", section: "Channels", url: "docs/channels.html#mastodon" },
    { title: "Bluesky (AT Protocol)", section: "Channels", url: "docs/channels.html#bluesky" },
    { title: "Viber", section: "Channels", url: "docs/channels.html#viber" },
    { title: "XMPP / Jabber", section: "Channels", url: "docs/channels.html#xmpp" },
    { title: "WebSocket / REST (generic)", section: "Channels", url: "docs/channels.html#websocket" },
    { title: "Nextcloud Talk", section: "Channels", url: "docs/channels.html#nextcloud" },
    // Configuration
    { title: "Configuration Reference", section: "Configuration", url: "docs/configuration.html" },
    { title: "~/.neuralcleave/config.toml", section: "Configuration", url: "docs/configuration.html#path" },
    { title: "gateway section", section: "Configuration", url: "docs/configuration.html#gateway" },
    { title: "models section", section: "Configuration", url: "docs/configuration.html#models" },
    { title: "memory section", section: "Configuration", url: "docs/configuration.html#memory" },
    { title: "voice section", section: "Configuration", url: "docs/configuration.html#voice" },
    { title: "ENV: secret resolution", section: "Configuration", url: "docs/configuration.html#env-secrets" },
    // CLI
    { title: "CLI Reference", section: "CLI", url: "docs/cli.html" },
    { title: "neuralcleave start", section: "CLI", url: "docs/cli.html#start" },
    { title: "neuralcleave init", section: "CLI", url: "docs/cli.html#init" },
    { title: "neuralcleave chat", section: "CLI", url: "docs/cli.html#chat" },
    { title: "neuralcleave plugins", section: "CLI", url: "docs/cli.html#plugins" },
    { title: "neuralcleave hub", section: "CLI", url: "docs/cli.html#hub" },
    { title: "neuralcleave orchestrate", section: "CLI", url: "docs/cli.html#orchestrate" },
    { title: "neuralcleave voice", section: "CLI", url: "docs/cli.html#voice" },
    { title: "neuralcleave autostart", section: "CLI", url: "docs/cli.html#autostart" },
    { title: "neuralcleave canvas", section: "CLI", url: "docs/cli.html#canvas" },
    { title: "neuralcleave cloud", section: "CLI", url: "docs/cli.html#cloud" },
    { title: "neuralcleave skills", section: "CLI", url: "docs/cli.html#skills" },
    { title: "neuralcleave sandbox", section: "CLI", url: "docs/cli.html#sandbox" },
    // REST API
    { title: "REST API Reference", section: "API", url: "docs/api.html" },
    { title: "POST /api/v1/chat", section: "API", url: "docs/api.html#chat" },
    { title: "GET /api/v1/health", section: "API", url: "docs/api.html#health" },
    { title: "GET /api/v1/memory", section: "API", url: "docs/api.html#memory" },
    { title: "GET /api/v1/plugins", section: "API", url: "docs/api.html#plugins" },
    { title: "GET /api/v1/hub/packages", section: "API", url: "docs/api.html#hub" },
    { title: "GET /api/v1/canvas/state", section: "API", url: "docs/api.html#canvas" },
    { title: "GET /api/v1/orchestrator/nodes", section: "API", url: "docs/api.html#orchestrator" },
    { title: "WebSocket /ws/chat", section: "API", url: "docs/api.html#ws-chat" },
    { title: "WebSocket /ws/canvas", section: "API", url: "docs/api.html#ws-canvas" },
    // Plugins
    { title: "Plugin SDK", section: "Plugins", url: "docs/plugins.html" },
    { title: "Writing a Plugin (Tool)", section: "Plugins", url: "docs/plugins.html#tool-plugin" },
    { title: "Writing a Channel Adapter", section: "Plugins", url: "docs/plugins.html#channel-plugin" },
    { title: "Plugin entry-points (pyproject.toml)", section: "Plugins", url: "docs/plugins.html#entry-points" },
    { title: "PluginRegistry", section: "Plugins", url: "docs/plugins.html#registry" },
    { title: "Hot-reload (POST /api/v1/plugins/{name}/reload)", section: "Plugins", url: "docs/plugins.html#reload" },
    { title: "NeuralCleave Hub marketplace", section: "Plugins", url: "docs/plugins.html#hub" },
    { title: "PackageScanner — safety checks", section: "Plugins", url: "docs/plugins.html#scanner" },
    // Voice
    { title: "Voice System", section: "Voice", url: "docs/voice.html" },
    { title: "STT — Whisper (faster-whisper)", section: "Voice", url: "docs/voice.html#stt" },
    { title: "TTS — ElevenLabs / Kokoro / pyttsx3", section: "Voice", url: "docs/voice.html#tts" },
    { title: "Wake word (OpenWakeWord)", section: "Voice", url: "docs/voice.html#wake-word" },
    { title: "Voice cloning (ElevenLabs)", section: "Voice", url: "docs/voice.html#cloning" },
    { title: "Continuous voice listener", section: "Voice", url: "docs/voice.html#continuous" },
    // Observability
    { title: "Observability — Prometheus + Logging", section: "Observability", url: "docs/observability.html" },
    { title: "13 Prometheus metrics", section: "Observability", url: "docs/observability.html#metrics" },
    { title: "GET /api/v1/metrics (Prometheus export)", section: "Observability", url: "docs/observability.html#endpoint" },
    { title: "Structured JSON logging", section: "Observability", url: "docs/observability.html#logging" },
    { title: "ContextLogger — per-session log binding", section: "Observability", url: "docs/observability.html#context-logger" },
    // Deployment
    { title: "Deployment", section: "Deployment", url: "docs/deployment.html" },
    { title: "Docker (single container)", section: "Deployment", url: "docs/deployment.html#docker" },
    { title: "docker-compose (Redis + Qdrant)", section: "Deployment", url: "docs/deployment.html#compose" },
    { title: "Railway", section: "Deployment", url: "docs/deployment.html#railway" },
    { title: "Render", section: "Deployment", url: "docs/deployment.html#render" },
    { title: "neuralcleave cloud CLI", section: "Deployment", url: "docs/deployment.html#cli" },
    // Testing
    { title: "Testing", section: "Testing", url: "docs/testing.html" },
    { title: "Running the test suite", section: "Testing", url: "docs/testing.html#running" },
    { title: "Test coverage by module", section: "Testing", url: "docs/testing.html#coverage" },
    { title: "Writing tests", section: "Testing", url: "docs/testing.html#writing" },
  ];

  const searchModal  = document.querySelector(".search-modal");
  const searchInput  = document.querySelector(".search-input");
  const searchResults = document.querySelector(".search-results");
  const navSearchEl  = document.querySelector(".nav-search");

  const openSearch = () => { if (searchModal) { searchModal.classList.add("open"); searchInput && searchInput.focus(); } };
  const closeSearch = () => { searchModal && searchModal.classList.remove("open"); };

  navSearchEl && navSearchEl.addEventListener("click", openSearch);
  navSearchEl && navSearchEl.addEventListener("focus", openSearch);

  document.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key === "k") { e.preventDefault(); openSearch(); }
    if (e.key === "Escape") closeSearch();
  });

  searchModal && searchModal.addEventListener("click", e => { if (e.target === searchModal) closeSearch(); });

  const doSearch = query => {
    if (!searchResults) return;
    const q = query.trim().toLowerCase();
    if (!q) { searchResults.innerHTML = ""; return; }

    const base = document.querySelector("base") ? "" : (window.location.pathname.endsWith("/docs/") || window.location.pathname.includes("/docs/") ? "../" : "");
    const hits = INDEX.filter(item => item.title.toLowerCase().includes(q) || item.section.toLowerCase().includes(q)).slice(0, 12);

    if (!hits.length) {
      searchResults.innerHTML = `<div class="search-empty">No results for "<strong>${q}</strong>"</div>`;
      return;
    }
    searchResults.innerHTML = hits.map(h => `
      <a class="search-result" href="${base}${h.url}">
        <div class="search-result-title">${h.title}</div>
        <div class="search-result-section">${h.section}</div>
      </a>`).join("");
  };

  searchInput && searchInput.addEventListener("input", e => doSearch(e.target.value));
  searchInput && searchInput.addEventListener("keydown", e => {
    if (e.key === "Enter") {
      const first = searchResults && searchResults.querySelector(".search-result");
      if (first) { first.click(); closeSearch(); }
    }
  });

})();
