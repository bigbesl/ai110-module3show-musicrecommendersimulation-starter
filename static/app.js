/**
 * WaveForm Web – D3.js graph renderer + HTML5 audio hover + search dropdown
 */

import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7/+esm";

// ─── State ────────────────────────────────────────────────────────────────────
let currentAudio    = null;
let simulation      = null;
let selectedTrackId = null;
let debounceTimer   = null;
let activeIndex     = -1;
let searchHistory   = JSON.parse(localStorage.getItem("wf_history") || "[]"); // [{id, title, artist, artworkUrl}]
let activeFilter    = "all";
let nodeGroup       = null;  // elevated for filter access
let linkSel         = null;  // elevated for filter access

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const form             = document.getElementById("search-form");
const input            = document.getElementById("search-input");
const dropdown         = document.getElementById("search-dropdown");
const svg              = document.getElementById("graph-svg");
const emptyState       = document.getElementById("empty-state");
const spinner          = document.getElementById("spinner");
const errorMsg         = document.getElementById("error-msg");
const errorText        = document.getElementById("error-text");
const tooltip          = document.getElementById("tooltip");
const tooltipArt       = document.getElementById("tooltip-art");
const tooltipTitle     = document.getElementById("tooltip-title");
const tooltipArtist    = document.getElementById("tooltip-artist");
const tooltipGenre     = document.getElementById("tooltip-genre");
const tooltipPlaying   = document.getElementById("tooltip-playing");
const tooltipNoPreview = document.getElementById("tooltip-no-preview");
const audioWave        = document.getElementById("audio-wave");
const historyBtn       = document.getElementById("history-btn");
const historyPanel     = document.getElementById("history-panel");
const historyList      = document.getElementById("history-list");
const historyClear     = document.getElementById("history-clear");
const bgColor          = document.getElementById("bg-color");
const bgVideoWrap      = document.getElementById("bg-video-wrap");
const bgIframe         = document.getElementById("bg-iframe");

// ─── Node visual config ───────────────────────────────────────────────────────
const NODE_RADIUS = { seed: 22, top_pick: 17, artist_match: 14, album_match: 15, style_match: 10 };
const NODE_COLOR  = {
  seed:         "#ff6b6b",
  top_pick:     "#ffd700",
  artist_match: "#4ecdc4",
  album_match:  "#c77dff",
  style_match:  "#a8a8c0",
};
const LINK_CLASS = {
  artist_match: "link-artist",
  album_match:  "link-album",
  style_match:  "link-style",
};
const LINK_DISTANCE = {
  artist_match: 150,
  album_match:  110,
  style_match:  200,
};

// ─── Search form ──────────────────────────────────────────────────────────────
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  closeDropdown();
  const query = input.value.trim();
  if (!query) return;
  if (selectedTrackId) {
    await loadGraphById(selectedTrackId);
  } else {
    await loadGraph(query);
  }
});

// ─── Dropdown: debounced input ────────────────────────────────────────────────
input.addEventListener("input", () => {
  selectedTrackId = null;
  clearTimeout(debounceTimer);
  const q = input.value.trim();
  if (q.length < 2) { closeDropdown(); return; }
  debounceTimer = setTimeout(() => fetchSuggestions(q), 150);
});

// ─── Dropdown: keyboard navigation ───────────────────────────────────────────
input.addEventListener("keydown", (e) => {
  const items = dropdown.querySelectorAll(".dropdown-item");
  if (!items.length) return;
  if (e.key === "ArrowDown") {
    e.preventDefault();
    activeIndex = Math.min(activeIndex + 1, items.length - 1);
    updateActive(items);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    activeIndex = Math.max(activeIndex - 1, 0);
    updateActive(items);
  } else if (e.key === "Enter" && activeIndex >= 0) {
    e.preventDefault();
    items[activeIndex].click();
  } else if (e.key === "Escape") {
    closeDropdown();
  }
});

function updateActive(items) {
  items.forEach((el, i) => el.classList.toggle("active", i === activeIndex));
  items[activeIndex]?.scrollIntoView({ block: "nearest" });
}

document.addEventListener("click", (e) => {
  if (!form.contains(e.target) && !dropdown.contains(e.target)) closeDropdown();
});

// ─── Suggestions ─────────────────────────────────────────────────────────────
async function fetchSuggestions(q) {
  showDropdownLoading();
  try {
    const resp = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    if (!resp.ok) { closeDropdown(); return; }
    const data = await resp.json();
    renderDropdown(data.results || []);
  } catch {
    closeDropdown();
  }
}

function renderDropdown(results) {
  activeIndex = -1;
  if (!results.length) {
    dropdown.innerHTML = `<div class="dropdown-no-results">No results found</div>`;
    openDropdown();
    return;
  }
  dropdown.innerHTML = results.map((r, i) => `
    <div class="dropdown-item" data-index="${i}" data-track-id="${r.trackId}" role="option">
      <img class="dropdown-art" src="${r.artworkUrl || ''}" alt="" loading="lazy" />
      <div class="dropdown-meta">
        <div class="dropdown-title">${escHtml(r.title)}</div>
        <div class="dropdown-artist">${escHtml(r.artist)}</div>
        <div class="dropdown-album">${escHtml(r.album || r.genre)}</div>
      </div>
    </div>
  `).join("");

  dropdown.querySelectorAll(".dropdown-item").forEach((el) => {
    el.addEventListener("click", () => {
      const trackId = el.dataset.trackId;
      const idx     = parseInt(el.dataset.index);
      const r       = results[idx];
      input.value     = `${r.title} — ${r.artist}`;
      selectedTrackId = trackId;
      closeDropdown();
      loadGraphById(trackId);
    });
  });
  openDropdown();
}

function showDropdownLoading() {
  dropdown.innerHTML = `<div class="dropdown-loading"><div class="mini-spin"></div> Searching…</div>`;
  openDropdown();
}

function openDropdown() {
  // Position the dropdown directly below the search input using fixed coords
  const rect = input.getBoundingClientRect();
  dropdown.style.top   = `${rect.bottom}px`;
  dropdown.style.left  = `${rect.left}px`;
  dropdown.style.width = `${rect.width}px`;
  dropdown.classList.remove("hidden");
  input.setAttribute("aria-expanded", "true");
}

function closeDropdown() {
  dropdown.classList.add("hidden");
  input.setAttribute("aria-expanded", "false");
  activeIndex = -1;
}

// ─── History ──────────────────────────────────────────────────────────────────
function pushHistory(seed) {
  // Remove duplicate if same track was searched before
  searchHistory = searchHistory.filter(h => h.id !== seed.id);
  searchHistory.unshift({ id: seed.id, title: seed.label, artist: seed.artist, artworkUrl: seed.artworkUrl || "" });
  if (searchHistory.length > 20) searchHistory.pop();
  localStorage.setItem("wf_history", JSON.stringify(searchHistory));
}

function renderHistoryPanel() {
  historyList.innerHTML = "";
  if (!searchHistory.length) {
    historyList.innerHTML = `<div class="history-empty">No searches yet</div>`;
    return;
  }
  searchHistory.forEach(h => {
    const item = document.createElement("div");
    item.className = "history-item";
    item.innerHTML = `
      ${h.artworkUrl
        ? `<img class="history-art" src="${h.artworkUrl}" alt="" />`
        : `<div class="history-art-placeholder">♪</div>`}
      <div class="history-info">
        <div class="history-title">${h.title}</div>
        <div class="history-artist">${h.artist}</div>
      </div>`;
    item.addEventListener("click", () => {
      closeHistoryPanel();
      loadGraphById(h.id);
    });
    historyList.appendChild(item);
  });
}

function openHistoryPanel() {
  renderHistoryPanel();
  historyPanel.classList.remove("hidden");
  historyBtn.classList.add("active");
}

function closeHistoryPanel() {
  historyPanel.classList.add("hidden");
  historyBtn.classList.remove("active");
}

historyBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  historyPanel.classList.contains("hidden") ? openHistoryPanel() : closeHistoryPanel();
});

historyClear.addEventListener("click", (e) => {
  e.stopPropagation();
  searchHistory = [];
  localStorage.removeItem("wf_history");
  renderHistoryPanel();
});

document.addEventListener("click", (e) => {
  if (!historyPanel.contains(e.target) && e.target !== historyBtn) {
    closeHistoryPanel();
  }
});

// ─── Graph loading ────────────────────────────────────────────────────────────
async function loadGraphById(trackId, fallbackTitle, fallbackArtist) {
  stopAudio();
  showSpinner();
  try {
    let resp = await fetch(`/api/graph?trackId=${encodeURIComponent(trackId)}`);
    // If ID lookup fails and we have title+artist, retry as text search
    if (!resp.ok && fallbackTitle && fallbackArtist) {
      resp = await fetch(`/api/graph?song=${encodeURIComponent(`${fallbackTitle} ${fallbackArtist}`)}`);
    }
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      showError(body.detail || "Song not found.");
      return;
    }
    const data = await resp.json();
    renderGraph(data.graph, data.seed);
  } catch {
    showError("Network error – make sure the server is running.");
  }
}

async function loadGraph(query) {
  stopAudio();
  showSpinner();
  try {
    const resp = await fetch(`/api/graph?song=${encodeURIComponent(query)}`);
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      showError(body.detail || "Song not found. Try a different title.");
      return;
    }
    const data = await resp.json();
    renderGraph(data.graph, data.seed);
  } catch {
    showError("Network error – make sure the server is running.");
  }
}

// ─── D3 render ────────────────────────────────────────────────────────────────
function renderGraph(graphData, seed) {
  pushHistory(seed);
  if (simulation) simulation.stop();
  d3.select(svg).selectAll("*").remove();

  const W = svg.clientWidth  || window.innerWidth;
  const H = svg.clientHeight || (window.innerHeight - 60);
  const svgSel = d3.select(svg).attr("viewBox", `0 0 ${W} ${H}`);

  // Defs: glow + clip paths
  const defs = svgSel.append("defs");
  const glow = defs.append("filter").attr("id", "glow")
    .attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%");
  glow.append("feGaussianBlur").attr("stdDeviation", "4").attr("result", "blur");
  const glowMerge = glow.append("feMerge");
  glowMerge.append("feMergeNode").attr("in", "blur");
  glowMerge.append("feMergeNode").attr("in", "SourceGraphic");

  graphData.nodes.forEach((n) => {
    defs.append("clipPath").attr("id", `clip-${n.id}`)
      .append("circle").attr("r", NODE_RADIUS[n.nodeType] || 10);
  });

  const g = svgSel.append("g").attr("class", "graph-root");
  svgSel.call(
    d3.zoom().scaleExtent([0.3, 3])
      .on("zoom", (event) => g.attr("transform", event.transform))
  );

  // Reset filter state on new graph
  activeFilter = "all";
  document.querySelectorAll(".legend-item").forEach(el => {
    el.classList.toggle("active", el.dataset.filter === "all");
  });

  // Links (module-level)
  linkSel = g.append("g").attr("class", "links")
    .selectAll("line").data(graphData.links).join("line")
    .attr("class", (d) => LINK_CLASS[d.linkType] || "link-style");

  // Node groups (module-level)
  nodeGroup = g.append("g").attr("class", "nodes")
    .selectAll("g").data(graphData.nodes).join("g")
    .attr("class", "node-group")
    .call(d3.drag()
      .on("start", dragStarted)
      .on("drag",  dragged)
      .on("end",   dragEnded)
    );

  // Pulse ring (seed + top_pick)
  nodeGroup.filter((d) => d.nodeType === "top_pick" || d.nodeType === "seed")
    .append("circle").attr("class", "pulse-ring")
    .attr("r", (d) => NODE_RADIUS[d.nodeType])
    .attr("fill", "none")
    .attr("stroke", (d) => NODE_COLOR[d.nodeType])
    .attr("stroke-width", 1.5).attr("opacity", 0)
    .each(function (d) { animatePulse(d3.select(this), NODE_RADIUS[d.nodeType]); });

  // Coloured ring
  nodeGroup.append("circle").attr("class", "node-ring")
    .attr("r", (d) => NODE_RADIUS[d.nodeType] + 3)
    .attr("fill", "none")
    .attr("stroke", (d) => NODE_COLOR[d.nodeType])
    .attr("stroke-width", (d) => d.nodeType === "seed" ? 3 : 1.5)
    .attr("opacity", 0.9)
    .attr("filter", (d) =>
      (d.nodeType === "seed" || d.nodeType === "top_pick") ? "url(#glow)" : null
    );

  // Fallback fill circle (visible when artwork is missing or fails to load)
  nodeGroup.append("circle").attr("class", "node-fill")
    .attr("r", (d) => NODE_RADIUS[d.nodeType])
    .attr("fill", (d) => NODE_COLOR[d.nodeType])
    .attr("opacity", 0.25);

  // Album art — rendered on top of fallback fill
  nodeGroup.append("image")
    .attr("href", (d) => d.artworkUrl || "")
    .attr("x", (d) => -NODE_RADIUS[d.nodeType])
    .attr("y", (d) => -NODE_RADIUS[d.nodeType])
    .attr("width",  (d) => NODE_RADIUS[d.nodeType] * 2)
    .attr("height", (d) => NODE_RADIUS[d.nodeType] * 2)
    .attr("clip-path", (d) => `url(#clip-${d.id})`)
    .attr("preserveAspectRatio", "xMidYMid slice")
    .attr("opacity", 0)   // hidden until loaded
    .on("load", function () {
      // Fade in once the image has loaded successfully
      d3.select(this).transition().duration(300).attr("opacity", 1);
    })
    .on("error", function () {
      // Keep the fallback fill visible; remove this broken image element
      d3.select(this).remove();
    });

  // Labels
  nodeGroup.append("text").attr("class", "node-label")
    .attr("dy", (d) => NODE_RADIUS[d.nodeType] + 14)
    .text((d) => truncate(d.label, d.nodeType === "seed" ? 22 : 16));

  // Hover / click
  nodeGroup
    .on("mouseenter", (event, d) => handleHoverIn(event, d))
    .on("mousemove",  (event)    => positionTooltip(event))
    .on("mouseleave", ()         => handleHoverOut())
    .on("click", (event, d) => {
      if (d.nodeType !== "seed") {
        input.value     = `${d.label} — ${d.artist}`;
        selectedTrackId = d.id;
        loadGraphById(d.id, d.label, d.artist);
      }
    });

  // Force simulation
  simulation = d3.forceSimulation(graphData.nodes)
    .force("link", d3.forceLink(graphData.links).id((d) => d.id)
      .distance((d) => LINK_DISTANCE[d.linkType] || 200)
      .strength(0.4)
    )
    .force("charge",    d3.forceManyBody().strength(-320))
    .force("center",    d3.forceCenter(W / 2, H / 2))
    .force("collision", d3.forceCollide().radius((d) => NODE_RADIUS[d.nodeType] + 16))
    .on("tick", () => {
      linkSel
        .attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y)
        .attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
      nodeGroup.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

  const seedNode = graphData.nodes.find((n) => n.nodeType === "seed");
  if (seedNode) { seedNode.fx = W / 2; seedNode.fy = H / 2; }

  nodeGroup.attr("opacity", 0)
    .transition().delay((_, i) => i * 25).duration(400).attr("opacity", 1);

  showGraph();
}

// ─── Audio hover ──────────────────────────────────────────────────────────────
function handleHoverIn(event, d) {
  showTooltip(event, d);
  triggerBackground(d);  // start video or color — may replace Deezer audio
  if (d.previewUrl) {
    stopAudio();
    currentAudio = new Audio(d.previewUrl);
    currentAudio.volume = 0.55;
    currentAudio.play().catch(() => {});
    currentAudio.addEventListener("ended", () => {
      audioWave.classList.remove("playing");
      currentAudio = null;
    });
    audioWave.classList.add("playing");
    tooltipPlaying.classList.remove("hidden");
    tooltipNoPreview.classList.add("hidden");
  } else {
    tooltipPlaying.classList.add("hidden");
    tooltipNoPreview.classList.remove("hidden");
  }
}
function handleHoverOut() {
  hideTooltip();
  stopAudio();
  audioWave.classList.remove("playing");
  clearBackground();
}
function stopAudio() {
  if (currentAudio) { currentAudio.pause(); currentAudio.currentTime = 0; currentAudio = null; }
}

// ─── Background video / color ─────────────────────────────────────────────────
let _bgVideoTimeout = null;
let _currentHoverId = null;  // tracks which node is being hovered to prevent stale async writes

async function triggerBackground(d) {
  const myId = d.id;
  _currentHoverId = myId;

  // Clear previous background immediately
  bgColor.style.opacity = "0";
  bgVideoWrap.style.opacity = "0";
  clearTimeout(_bgVideoTimeout);

  // Always show a color gradient immediately — extract from artwork or use default teal
  (d.artworkUrl ? extractDominantColor(d.artworkUrl) : Promise.resolve("rgba(78,205,196,0.55)"))
    .then(color => {
      if (_currentHoverId !== myId) return;
      if (bgVideoWrap.style.opacity === "0" || bgVideoWrap.style.opacity === "") {
        bgColor.style.background =
          `radial-gradient(ellipse 80% 60% at 50% 40%, ${color} 0%, transparent 70%)`;
        bgColor.style.opacity = "1";
      }
    });

  // Try YouTube in parallel — if it finds a video, it replaces the color
  try {
    const resp = await fetch(
      `/api/youtube?artist=${encodeURIComponent(d.artist)}&title=${encodeURIComponent(d.label)}`
    );
    const { videoId } = await resp.json().catch(() => ({ videoId: null }));

    if (_currentHoverId !== myId) return;

    if (videoId) {
      bgIframe.src =
        `https://www.youtube.com/embed/${videoId}` +
        `?autoplay=1&mute=1&controls=0&loop=1&playlist=${videoId}&rel=0&modestbranding=1`;
      bgColor.style.opacity = "0"; // hide color once video is ready
      bgVideoWrap.style.opacity = "1";
    }
  } catch { /* network error — color fallback already running */ }
}

function clearBackground() {
  _currentHoverId = null;
  bgColor.style.opacity = "0";
  bgVideoWrap.style.opacity = "0";
  clearTimeout(_bgVideoTimeout);
  _bgVideoTimeout = setTimeout(() => { bgIframe.src = ""; }, 900);
}

async function extractDominantColor(url) {
  return new Promise(resolve => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      try {
        const c = document.createElement("canvas");
        c.width = 10; c.height = 10;
        c.getContext("2d").drawImage(img, 0, 0, 10, 10);
        const px = c.getContext("2d").getImageData(4, 4, 1, 1).data;
        resolve(`rgba(${px[0]},${px[1]},${px[2]},0.55)`);
      } catch { resolve("rgba(78,205,196,0.55)"); }
    };
    img.onerror = () => resolve("rgba(78,205,196,0.55)");
    img.src = url;
  });
}

// ─── Legend filter ────────────────────────────────────────────────────────────
function applyFilter(type) {
  activeFilter = type;
  document.querySelectorAll(".legend-item").forEach(el => {
    el.classList.toggle("active", el.dataset.filter === type);
  });
  if (!nodeGroup || !linkSel) return;
  nodeGroup.transition().duration(200).style("opacity", d => {
    if (type === "all") return 1;
    if (d.nodeType === "seed") return 1;
    return d.nodeType === type ? 1 : 0.06;
  });
  linkSel.transition().duration(200).style("opacity", d => {
    if (type === "all") return null;
    return d.linkType === type ? 1 : 0.04;
  });
}

document.querySelectorAll(".legend-item").forEach(el => {
  el.addEventListener("click", () => applyFilter(el.dataset.filter));
});

// ─── Tooltip ─────────────────────────────────────────────────────────────────
function showTooltip(event, d) {
  tooltipArt.src = d.artworkUrl || "";
  tooltipTitle.textContent  = d.label;
  tooltipArtist.textContent = d.artist;
  tooltipGenre.textContent  = d.genre + (d.releaseYear ? ` · ${d.releaseYear}` : "");
  tooltip.classList.remove("hidden");
  positionTooltip(event);
}
function hideTooltip() { tooltip.classList.add("hidden"); }
function positionTooltip(event) {
  const pad = 16, tw = tooltip.offsetWidth || 260, th = tooltip.offsetHeight || 80;
  let x = event.clientX + pad, y = event.clientY + pad;
  if (x + tw > window.innerWidth)  x = event.clientX - tw - pad;
  if (y + th > window.innerHeight) y = event.clientY - th - pad;
  tooltip.style.left = `${x}px`;
  tooltip.style.top  = `${y}px`;
}

// ─── Drag ─────────────────────────────────────────────────────────────────────
function dragStarted(event, d) {
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x; d.fy = d.y;
}
function dragged(event, d) { d.fx = event.x; d.fy = event.y; }
function dragEnded(event, d) {
  if (!event.active) simulation.alphaTarget(0);
  if (d.nodeType !== "seed") { d.fx = null; d.fy = null; }
}

// ─── Pulse ────────────────────────────────────────────────────────────────────
function animatePulse(sel, baseR) {
  sel.attr("r", baseR).attr("opacity", 0.7)
    .transition().duration(1600).ease(d3.easeExpOut)
    .attr("r", baseR + 12).attr("opacity", 0)
    .on("end", function () { animatePulse(d3.select(this), baseR); });
}

// ─── UI state ─────────────────────────────────────────────────────────────────
function showSpinner() {
  emptyState.classList.add("hidden");
  errorMsg.classList.add("hidden");
  spinner.classList.remove("hidden");
  d3.select(svg).selectAll("*").remove();
}
function showGraph() {
  spinner.classList.add("hidden");
  emptyState.classList.add("hidden");
  errorMsg.classList.add("hidden");
}
function showError(msg) {
  spinner.classList.add("hidden");
  emptyState.classList.add("hidden");
  errorText.textContent = msg;
  errorMsg.classList.remove("hidden");
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
function truncate(str, maxLen) {
  return str.length <= maxLen ? str : str.slice(0, maxLen - 1) + "…";
}
function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// Press "/" to focus search bar
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement !== input) {
    e.preventDefault();
    input.focus();
  }
});
