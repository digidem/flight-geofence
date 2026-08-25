// Minimal fallback translations (used before /api/i18n loads)
const fallbackTranslations = {
  pt: {
    login_title: "Interface de monitoramento protegida",
    login_subtitle: "Use a senha configurada como",
    login_button: "Entrar",
    login_password_label: "Senha",
    app_title: "Flight Geofence Alerts",
  },
  en: {
    login_title: "Protected monitoring interface",
    login_subtitle: "Use the password configured as",
    login_button: "Log in",
    login_password_label: "Password",
    app_title: "Flight Geofence Alerts",
  },
};

// Timezone offsets
const timezoneOffsets = {
  "UTC": 0,
  "America/Sao_Paulo": -3,
  "America/Manaus": -4,
  "America/Belem": -3,
  "America/Rio_Branco": -5,
  "America/Noronha": -2,
};

const appState = {
  csrfToken: null,
  settings: null,
  areas: [],
  events: [],
  areaFilter: { search: "", category: "", selected: "" },
  language: "en",
  timezone: "America/Sao_Paulo",
  translations: fallbackTranslations,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

function t(key) {
  const lang = appState.language || "en";
  const dict = appState.translations || fallbackTranslations;
  return (dict[lang] && dict[lang][key]) || (dict.en && dict.en[key]) || key;
}

function detectBrowserLanguage() {
  const browserLang = navigator.language || navigator.userLanguage || "en";
  const langCode = browserLang.toLowerCase().split("-")[0];
  return langCode === "pt" ? "pt" : "en";
}

function updateHtmlLang() {
  document.documentElement.lang = appState.language === "pt" ? "pt-br" : "en";
}

function isMutation(method) {
  return ["POST", "PUT", "PATCH", "DELETE"].includes(method.toUpperCase());
}

async function api(url, options = {}) {
  const method = options.method || "GET";
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  if (isMutation(method) && appState.csrfToken && url !== "/api/auth/login") {
    headers["X-CSRF-Token"] = appState.csrfToken;
  }
  const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
  let body = {};
  try {
    body = await response.json();
  } catch {
    body = { detail: response.statusText };
  }
  if (response.status === 401) showLogin();
  if (!response.ok) throw new Error(body.detail || body.error || response.statusText);
  return body;
}

function showLogin() {
  $("#login-screen").hidden = false;
  $("#app").hidden = true;
  appState.csrfToken = null;
  applyTranslations();
}

function showApp() {
  $("#login-screen").hidden = true;
  $("#app").hidden = false;
}

function formatTime(value) {
  if (!value) return "—";
  try {
    const dt = new Date(value);
    const lang = appState.language || "en";
    const offset = timezoneOffsets[appState.timezone] || 0;

    const utcMs = dt.getTime() + dt.getTimezoneOffset() * 60000;
    const localMs = utcMs + offset * 3600000;
    const localDate = new Date(localMs);

    const dayNames = lang === "pt"
      ? ["Domingo", "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado"]
      : ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

    const dayName = dayNames[localDate.getUTCDay()];
    const day = String(localDate.getUTCDate()).padStart(2, "0");
    const month = String(localDate.getUTCMonth() + 1).padStart(2, "0");
    const year = localDate.getUTCFullYear();
    const hours = String(localDate.getUTCHours()).padStart(2, "0");
    const mins = String(localDate.getUTCMinutes()).padStart(2, "0");

    const separator = t("time_at");
    return `${dayName} ${day}/${month}/${year}${separator}${hours}:${mins}`;
  } catch {
    return value;
  }
}

function metric(label, value, note) {
  return `<article class="metric"><div class="metric-label">${escapeHtml(label)}</div><div class="metric-value">${escapeHtml(value)}</div><div class="metric-note">${escapeHtml(note)}</div></article>`;
}

function fr24ClusterNumericBounds(cluster) {
  const values = cluster.use_manual_bounds
    ? [cluster.manual_north, cluster.manual_south, cluster.manual_west, cluster.manual_east]
    : [cluster.calc_north, cluster.calc_south, cluster.calc_west, cluster.calc_east];
  if (values.some((value) => value === null || value === undefined)) return null;
  return { north: values[0], south: values[1], west: values[2], east: values[3] };
}

function fr24ClusterBoundsText(cluster) {
  const bounds = fr24ClusterNumericBounds(cluster);
  if (!bounds) return t("fr24_bounds_pending");
  return `N ${bounds.north} · S ${bounds.south} · W ${bounds.west} · E ${bounds.east}`;
}

function fr24CoverageMinimap(cluster) {
  // Equirectangular sketch of the cluster coverage: member-area polygons
  // filled, the FR24 query rectangle dashed on top. Purely visual sanity
  // check for operators -- "is this really the territory I think it is?"
  const fc = cluster.coverage_geojson;
  const bounds = fr24ClusterNumericBounds(cluster);
  if (!fc || !Array.isArray(fc.features) || !bounds) return "";
  const latSpan = bounds.north - bounds.south;
  const lonSpan = bounds.east - bounds.west;
  if (latSpan <= 0 || lonSpan <= 0) return "";
  const width = 260;
  const kx = Math.cos(((bounds.north + bounds.south) / 2) * (Math.PI / 180)) || 1;
  const height = Math.max(70, Math.min(200, Math.round(width * (latSpan / (lonSpan * kx)))));
  const pad = 6;
  const px = (lon) => pad + ((lon - bounds.west) / lonSpan) * (width - 2 * pad);
  const py = (lat) => pad + ((bounds.north - lat) / latSpan) * (height - 2 * pad);
  const ringPath = (ring) =>
    ring.map(([lon, lat], i) => `${i ? "L" : "M"}${px(lon).toFixed(2)} ${py(lat).toFixed(2)}`).join("") + "Z";
  const geomPaths = (geom) => {
    if (!geom) return "";
    if (geom.type === "Polygon") return geom.coordinates.map(ringPath).join("");
    if (geom.type === "MultiPolygon") {
      return geom.coordinates.map((poly) => poly.map(ringPath).join("")).join("");
    }
    return "";
  };
  const areas = fc.features
    .filter((f) => f.properties && f.properties.role === "area")
    .map(
      (f) =>
        `<path class="minimap-area" fill-rule="evenodd" d="${geomPaths(f.geometry)}"><title>${escapeHtml(f.properties.name || "")}</title></path>`,
    )
    .join("");
  const bx0 = px(bounds.west).toFixed(2);
  const by0 = py(bounds.north).toFixed(2);
  const bw = (px(bounds.east) - px(bounds.west)).toFixed(2);
  const bh = (py(bounds.south) - py(bounds.north)).toFixed(2);
  const rect = `<rect class="minimap-bounds" x="${bx0}" y="${by0}" width="${bw}" height="${bh}"/>`;
  return `<svg class="fr24-minimap" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(t("fr24_minimap_aria"))}">${areas}${rect}</svg>`;
}

function fr24ClusterCard(cluster) {
  const missing = cluster.missing_area_ids && cluster.missing_area_ids.length
    ? `<p class="error">${t("fr24_missing_areas")}: ${cluster.missing_area_ids.length}</p>`
    : "";
  const errorLine = cluster.last_error ? `<p class="error">${escapeHtml(cluster.last_error)}</p>` : "";
  return `<article class="review-card" data-id="${escapeHtml(cluster.id)}">
    <div>
      <strong>${escapeHtml(cluster.name)}</strong>${cluster.enabled ? "" : ` · <span class="muted">${t("fr24_disabled")}</span>`}
      <p class="muted">${fr24ClusterBoundsText(cluster)}</p>
      ${fr24CoverageMinimap(cluster)}
      <p class="muted">${t("fr24_cluster_areas")}: ${cluster.area_ids.length} · ${t("fr24_last_poll")}: ${cluster.last_poll_at ? formatTime(cluster.last_poll_at) : "—"} · ${t("fr24_last_credits")}: ${cluster.last_estimated_credits ?? "—"}</p>
      ${errorLine}${missing}
    </div>
    <button class="button ghost dark fr24-edit">${t("fr24_edit")}</button>
    <button class="button ghost dark fr24-delete">${t("fr24_delete")}</button>
  </article>`;
}

function fr24AreaPickerRows(selectedIds) {
  // Deliberately NOT appState.areas: that list reflects whatever search/
  // category filter is currently active on the "Protected areas" tab (or a
  // 500-row page of it). Rendering the picker from a filtered/paginated
  // list would mean any member area outside the current filter never shows
  // a checkbox at all -- and since submit only collects checked boxes that
  // ARE rendered, saving would silently drop that membership. This picker
  // always uses the dedicated, unfiltered fr24SelectedAreas fetch instead.
  const areas = appState.fr24SelectedAreas || [];
  if (!areas.length) return `<p class="muted">${t("fr24_no_selected_areas")}</p>`;
  return areas
    .map(
      (area) =>
        `<label class="check"><input type="checkbox" class="fr24-area-checkbox" value="${escapeHtml(area.id)}" ${selectedIds.includes(area.id) ? "checked" : ""}> ${escapeHtml(area.name)}</label>`,
    )
    .join("");
}

function fr24PopulateForm(cluster) {
  const form = $("#fr24-cluster-form");
  form.elements.namedItem("id").value = cluster.id;
  form.elements.namedItem("name").value = cluster.name;
  form.elements.namedItem("buffer_km").value = cluster.buffer_km;
  form.elements.namedItem("min_altitude_ft").value = cluster.min_altitude_ft;
  form.elements.namedItem("max_altitude_ft").value = cluster.max_altitude_ft;
  form.elements.namedItem("enabled").checked = Boolean(cluster.enabled);
  $$("input[name='categories']").forEach((box) => {
    box.checked = cluster.categories.includes(box.value);
  });
  form.elements.namedItem("use_manual_bounds").checked = Boolean(cluster.use_manual_bounds);
  $("#fr24-manual-bounds-fields").hidden = !cluster.use_manual_bounds;
  form.elements.namedItem("manual_north").value = cluster.manual_north ?? "";
  form.elements.namedItem("manual_south").value = cluster.manual_south ?? "";
  form.elements.namedItem("manual_west").value = cluster.manual_west ?? "";
  form.elements.namedItem("manual_east").value = cluster.manual_east ?? "";
  $("#fr24-area-picker").innerHTML = fr24AreaPickerRows(cluster.area_ids || []);
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

function fr24ResetForm() {
  const form = $("#fr24-cluster-form");
  form.reset();
  form.elements.namedItem("id").value = "";
  $("#fr24-manual-bounds-fields").hidden = true;
  $("#fr24-area-picker").innerHTML = fr24AreaPickerRows([]);
}

function fr24SourceNote(source) {
  if (source === "environment") return t("fr24_source_environment");
  if (source === "interface") return t("fr24_source_interface");
  return t("fr24_source_default");
}

function fr24LastRunText(latestPoll) {
  if (!latestPoll) return t("fr24_no_run_yet");
  const when = formatTime(latestPoll.completed_at || latestPoll.started_at);
  // skipped = the scheduler woke up and deliberately did nothing (kill
  // switch off, no clusters, budget pause). Rendering that as "failed"
  // scared operators for no reason, so it gets its own neutral wording.
  if (latestPoll.skipped) {
    return `${when} · ${t("fr24_run_skipped")}: ${latestPoll.error_message}`;
  }
  const outcome = latestPoll.error_message
    ? `${t("fr24_run_failed")}: ${latestPoll.error_message}`
    : t("fr24_run_success");
  return `${when} · ${outcome}`;
}

async function loadFr24() {
  // Dedicated, unfiltered, selected-only fetch for the area picker -- must
  // never depend on the "Protected areas" tab's own search/category filter
  // or on whether that tab has even been visited this session.
  const selectedAreasResult = await api("/api/areas?selected=true&limit=500");
  appState.fr24SelectedAreas = selectedAreasResult.items;
  const [status, clustersResult, settingsResult] = await Promise.all([
    api("/api/fr24/status"),
    api("/api/fr24/clusters"),
    api("/api/settings"),
  ]);

  // Kill-switch toggle: reflects FR24_ENABLED. When the value is pinned by
  // the environment the switch is disabled and the note says so, matching
  // how locked settings render on the Settings tab.
  const locked = status.enabled_source === "environment";
  const enableToggle = $("#fr24-enable-toggle");
  if (enableToggle) {
    enableToggle.checked = status.enabled;
    enableToggle.disabled = locked;
    enableToggle.title = locked ? t("fr24_locked_env") : "";
  }
  const powerBox = $("#fr24-power");
  if (powerBox) powerBox.classList.toggle("on", status.enabled);
  const powerState = $("#fr24-power-state");
  if (powerState) {
    powerState.textContent = status.enabled ? t("fr24_power_on") : t("fr24_power_off");
  }
  const powerNote = $("#fr24-power-note");
  if (powerNote) {
    const parts = [t("fr24_power_note"), fr24SourceNote(status.enabled_source)];
    if (locked) parts.push(t("fr24_locked_env"));
    powerNote.textContent = parts.join(" · ");
  }

  const blockerKeys = {
    flag_disabled: "fr24_blocker_flag_disabled",
    missing_api_key: "fr24_blocker_missing_api_key",
    no_enabled_clusters: "fr24_blocker_no_enabled_clusters",
    budget_exhausted_paused: "fr24_blocker_budget_exhausted_paused",
  };
  const blockers = (status.blockers || []).map((code) => t(blockerKeys[code] || code));
  $("#fr24-blockers").innerHTML = blockers.length
    ? `<div class="warning"><strong>${escapeHtml(t("fr24_blockers_title"))}:</strong> ${blockers.map(escapeHtml).join(" · ")}</div>`
    : "";

  // Budget policy control -- fed by its own GET /api/settings so value,
  // source, and locked stay server-authoritative. Options come from the
  // reported choices; setField() applies value + env lock to the select.
  const policyChoiceKeys = {
    warn_only: "fr24_policy_choice_warn_only",
    pause_fr24: "fr24_policy_choice_pause_fr24",
    continue_until_provider_rejects: "fr24_policy_choice_continue",
  };
  const policyForm = $("#fr24-budget-policy-form");
  if (policyForm) {
    const policy = settingsResult.settings.fr24_budget_policy;
    const policySelect = policyForm.elements.namedItem("fr24_budget_policy");
    policySelect.innerHTML = policy.choices
      .map((choice) => `<option value="${choice}">${escapeHtml(t(policyChoiceKeys[choice] || choice))}</option>`)
      .join("");
    setField(policyForm, "fr24_budget_policy", policy);
    $("#fr24-policy-current").textContent = t(policyChoiceKeys[policy.value] || policy.value);
    $("#fr24-policy-effect").textContent =
      policy.value === "pause_fr24"
        ? t("fr24_policy_effect_stop")
        : t("fr24_policy_effect_keep_polling");
    $("#fr24-policy-source").textContent = fr24SourceNote(policy.source);
    const policyBadge = $("#fr24-policy-env-badge");
    if (policyBadge) {
      policyBadge.textContent = t("fr24_policy_env_locked");
      policyBadge.hidden = !policy.locked;
    }
  }
  // FR24_ENABLED itself is shown by the switch above, not duplicated here.
  $("#fr24-status").innerHTML = [
    metric(
      t("fr24_api_key_label"),
      status.api_key_configured ? t("fr24_api_key_set") : t("fr24_api_key_missing"),
      fr24SourceNote(status.api_key_source),
    ),
    metric(t("fr24_last_run"), fr24LastRunText(status.latest_poll), ""),
    metric(t("fr24_active_clusters"), `${status.active_clusters}/${status.max_active_clusters}`, ""),
    metric(t("fr24_budget_state"), status.budget_state, ""),
    metric(t("fr24_credits_used"), `${status.credits_used_this_cycle} / ${status.operating_budget}`, status.billing_cycle_id),
    metric(t("fr24_baseline"), String(status.all_empty_baseline), ""),
    metric(
      t("fr24_projected"),
      status.projected_end_of_cycle_credits === null
        ? t("fr24_insufficient_data")
        : String(Math.round(status.projected_end_of_cycle_credits)),
      "",
    ),
  ].join("");
  $("#fr24-overlap-warning").textContent = status.overlap_warnings.length
    ? `${t("fr24_overlap_warning")}: ${status.overlap_warnings.map((pair) => pair.join(" / ")).join(", ")}`
    : "";

  appState.fr24Clusters = clustersResult.clusters;
  $("#fr24-cluster-list").innerHTML = clustersResult.clusters.length
    ? clustersResult.clusters.map(fr24ClusterCard).join("")
    : `<p class="muted">${t("fr24_no_clusters")}</p>`;
  $$("#fr24-cluster-list .review-card").forEach((card) => {
    const cluster = clustersResult.clusters.find((item) => item.id === card.dataset.id);
    if (!cluster) return;
    card.querySelector(".fr24-edit").addEventListener("click", () => fr24PopulateForm(cluster));
    card.querySelector(".fr24-delete").addEventListener("click", async () => {
      if (!window.confirm(`${t("fr24_delete")}: ${cluster.name}?`)) return;
      try {
        await api(`/api/fr24/clusters/${encodeURIComponent(cluster.id)}`, { method: "DELETE" });
        await loadFr24();
      } catch (error) {
        window.alert(error.message);
      }
    });
  });

  // Re-render the area picker preserving whatever's currently checked
  // (rather than always resetting) so a re-render triggered mid-edit --
  // e.g. by the language toggle -- doesn't discard an in-progress selection.
  const currentlyChecked = $$(".fr24-area-checkbox:checked").map((box) => box.value);
  $("#fr24-area-picker").innerHTML = fr24AreaPickerRows(currentlyChecked);
}

function eventLabel(type) {
  return type === "PROBABLE_STOP" ? t("event_probable_stop") : t("event_disappearance");
}

function translateClassification(classification) {
  const mapping = {
    scheduled_airline: "class_scheduled_airline",
    unknown_candidate: "class_unknown_candidate",
    non_airline_candidate: "class_non_airline_candidate",
  };
  return t(mapping[classification] || classification);
}

function translateCategory(category) {
  const mapping = {
    indigenous_territory: "category_indigenous_territory",
    conservation_unit: "category_conservation_unit",
  };
  return t(mapping[category] || category);
}

function aircraftHexLinks(hex) {
  if (!hex) return [];
  const h = hex.trim().toLowerCase();
  if (h.startsWith("~")) return [];
  if (!/^[0-9a-f]{6}$/.test(h)) return [];
  return [
    { label: "ADSB.lol", url: `https://globe.adsb.lol/?icao=${h}` },
    { label: "ADS-B Exchange", url: `https://globe.adsbexchange.com/?icao=${h}` },
    { label: "Airplanes.live", url: `https://globe.airplanes.live/?icao=${h}` },
  ];
}

function registrationLinks(registration) {
  if (!registration) return [];
  const reg = registration.trim().toUpperCase().replace(/-/g, "");
  if (!reg || reg.length < 2 || !/^[A-Z0-9]+$/.test(reg) || !/[A-Z]/.test(reg)) return [];
  const links = [];
  const brazilMatch = /^(PP|PR|PS|PT|PU)[A-Z0-9]{3}$/.test(reg);
  if (brazilMatch) {
    links.push({ label: "ANAC RAB", url: `https://aeronaves.anac.gov.br/aeronaves/cons_rab_print.asp?nf=${reg}` });
    links.push({ label: "Search ANAC RAB", url: "https://aeronaves.anac.gov.br/aeronaves/cons_rab.asp" });
  }
  links.push({ label: "Flightradar24", url: `https://www.flightradar24.com/data/aircraft/${reg.toLowerCase()}` });
  return links;
}

function callsignLinks(callsign) {
  if (!callsign) return [];
  const cs = callsign.trim().toUpperCase();
  if (!/^[A-Z0-9-]{2,12}$/.test(cs)) return [];
  return [{ label: "FlightAware", url: `https://www.flightaware.com/live/flight/${cs}` }];
}

function positionLinks(lat, lng) {
  if (lat == null || lng == null) return [];
  const latF = parseFloat(lat), lngF = parseFloat(lng);
  if (isNaN(latF) || isNaN(lngF) || !isFinite(latF) || !isFinite(lngF)) return [];
  if (latF < -90 || latF > 90 || lngF < -180 || lngF > 180) return [];
  const latS = latF.toFixed(6), lngS = lngF.toFixed(6);
  return [
    { label: "Google Maps", url: `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(latS + "," + lngS)}` },
    { label: "OpenStreetMap", url: `https://www.openstreetmap.org/?mlat=${latS}&mlon=${lngS}#map=13/${latS}/${lngS}` },
  ];
}

function airportLinks(icao, iata, ident) {
  const links = [];
  const seen = new Set();
  function add(label, url, priority) {
    if (!seen.has(url)) { seen.add(url); links.push({ label, url, priority }); }
  }
  if (icao) {
    const ic = icao.trim().toUpperCase();
    if (ic.length === 4 && ic.startsWith("S")) add("AISWEB", `https://aisweb.decea.mil.br/?codigo=${ic}&i=aerodromos`, 1);
    if (ic.length === 4 && /^[A-Z0-9]{4}$/.test(ic)) add("FlightAware", `https://www.flightaware.com/live/airport/${ic}`, 2);
  }
  if (ident) {
    const id = ident.trim().toUpperCase();
    if (id && /^[A-Z0-9]+$/.test(id)) add("OurAirports", `https://ourairports.com/airports/${id}/`, 3);
  }
  if (iata) {
    const ia = iata.trim().toUpperCase();
    if (ia.length === 3 && /^[A-Z]{3}$/.test(ia)) add("Flightradar24", `https://www.flightradar24.com/data/airports/${ia.toLowerCase()}`, 4);
  }
  return links.sort((a, b) => a.priority - b.priority);
}

function providerLinks(providerId) {
  const map = {
    adsb_lol: { label: "ADSB.lol", url: "https://adsb.lol/" },
    airplanes_live: { label: "Airplanes.live", url: "https://airplanes.live/" },
    adsbexchange: { label: "ADS-B Exchange", url: "https://www.adsbexchange.com/" },
    flightradar24: { label: "Flightradar24", url: "https://www.flightradar24.com/" },
  };
  return map[providerId] ? [map[providerId]] : [];
}

function eventRow(event) {
  const hex = event.aircraft_hex.toUpperCase();
  const hexLinks = aircraftHexLinks(event.aircraft_hex);
  const hexDisplay = hexLinks.length
    ? `<a href="${hexLinks[0].url}" target="_blank" rel="noopener noreferrer" style="color:var(--ink);text-decoration:underline">${escapeHtml(hex)}</a>`
    : escapeHtml(hex);
  const regLinks = registrationLinks(event.registration);
  const regDisplay = event.registration
    ? (regLinks.length ? `<a href="${regLinks[0].url}" target="_blank" rel="noopener noreferrer" class="link-forest">${escapeHtml(event.registration)}</a>` : escapeHtml(event.registration))
    : "—";
  return `<tr>
    <td>${escapeHtml(formatTime(event.occurred_at))}</td>
    <td><span class="signal ${event.event_type === "PROBABLE_STOP" ? "stop" : "disappeared"}">${eventLabel(event.event_type)}</span></td>
    <td><strong>${hexDisplay}</strong><div class="muted">${escapeHtml(event.callsign || "—")} · ${regDisplay} · ${escapeHtml(event.aircraft_type || "—")}</div></td>
    <td>${event.area_names.map(escapeHtml).join("<br>")}</td>
    <td>${escapeHtml(String(event.altitude_ft ?? "—"))} ft · ${escapeHtml(String(event.ground_speed_kt ?? "—"))} kt</td>
    <td>${escapeHtml(event.phase)}</td>
    <td>${escapeHtml(event.review_status)}</td>
  </tr>`;
}

async function loadEventDetail(eventId) {
  const container = $("#event-detail-content");
  if (!container) return;
  container.innerHTML = `<p class="muted">Loading…</p>`;
  try {
    const result = await api(`/api/events?limit=500`);
    const event = result.events.find((e) => e.id === eventId);
    if (!event) {
      const trackPanel = $("#event-track-panel");
      if (trackPanel) trackPanel.hidden = true;
      container.innerHTML = `<p class="muted">Event not found.</p>`;
      return;
    }
    const hexLinks = aircraftHexLinks(event.aircraft_hex);
    const regLinks = registrationLinks(event.registration);
    const csLinks = callsignLinks(event.callsign);
    const posLinks = positionLinks(event.latitude, event.longitude);
    const details = event.details || {};
    const providerLks = providerLinks(event.provider);

    const linkList = (links) => links.map((l) => `<a href="${escapeHtml(l.url)}" target="_blank" rel="noopener noreferrer" class="link-forest">${escapeHtml(l.label)}</a>`).join(" · ");

    const rows = [
      `<tr><td>${t("email_event")}</td><td><strong>${escapeHtml(eventLabel(event.event_type))}</strong></td></tr>`,
      `<tr><td>${t("email_time")}</td><td>${escapeHtml(formatTime(event.occurred_at))}</td></tr>`,
      `<tr><td>${t("email_aircraft")}</td><td><strong>${escapeHtml(event.aircraft_hex.toUpperCase())}</strong>${hexLinks.length ? " — " + linkList(hexLinks) : ""}</td></tr>`,
    ];
    if (event.callsign) rows.push(`<tr><td>${t("email_callsign")}</td><td>${escapeHtml(event.callsign)}${csLinks.length ? " — " + linkList(csLinks) : ""}</td></tr>`);
    if (event.registration) rows.push(`<tr><td>${t("email_registration")}</td><td>${escapeHtml(event.registration)}${regLinks.length ? " — " + linkList(regLinks) : ""}</td></tr>`);
    if (event.aircraft_type) rows.push(`<tr><td>${t("email_aircraft_type")}</td><td>${escapeHtml(event.aircraft_type)}</td></tr>`);
    if (event.area_names.length) rows.push(`<tr><td>${t("email_protected_areas")}</td><td>${event.area_names.map(escapeHtml).join(", ")}</td></tr>`);
    if (event.latitude != null && event.longitude != null) {
      const latF = parseFloat(event.latitude), lngF = parseFloat(event.longitude);
      rows.push(`<tr><td>${t("email_last_position")}</td><td>${escapeHtml(latF.toFixed(6))}, ${escapeHtml(lngF.toFixed(6))}${posLinks.length ? " — " + linkList(posLinks) : ""}</td></tr>`);
    }
    if (event.altitude_ft != null) rows.push(`<tr><td>${t("email_altitude")}</td><td>${escapeHtml(String(event.altitude_ft))} ft MSL</td></tr>`);
    if (event.ground_speed_kt != null) rows.push(`<tr><td>${t("email_ground_speed")}</td><td>${escapeHtml(String(event.ground_speed_kt))} kt</td></tr>`);
    if (event.provider) rows.push(`<tr><td>${t("email_provider")}</td><td>${escapeHtml(event.provider)}${providerLks.length ? " — " + linkList(providerLks) : ""}</td></tr>`);
    if (details.source_type) rows.push(`<tr><td>${t("email_source_type")}</td><td>${escapeHtml(details.source_type)}</td></tr>`);
    if (details.origin) rows.push(`<tr><td>${t("email_origin")}</td><td>${escapeHtml(details.origin)}</td></tr>`);
    if (details.destination) rows.push(`<tr><td>${t("email_destination")}</td><td>${escapeHtml(details.destination)}</td></tr>`);
    rows.push(`<tr><td>${t("email_reason")}</td><td>${escapeHtml(event.reason)}</td></tr>`);
    rows.push(`<tr><td>${t("email_classification")}</td><td>${escapeHtml(translateClassification(event.airline_classification))}</td></tr>`);

    container.innerHTML = `
      <h3>${escapeHtml(eventLabel(event.event_type))} — ${escapeHtml(event.aircraft_hex.toUpperCase())}</h3>
      <table style="width:100%;border-collapse:collapse;font-size:14px">${rows.join("")}</table>
      <p style="margin-top:16px"><a href="/">&larr; Back to dashboard</a></p>`;
    await setupEventTrackPanel(event);
  } catch (error) {
    container.innerHTML = `<p class="muted">Error loading event: ${escapeHtml(error.message)}</p>`;
  }
}


const TRACK_BLOCKED_KEYS = {
  missing_fr24_id: "fr24_track_blocked_missing",
  already_fetched: "fr24_track_blocked_fetched",
  budget_exhausted_pause_fr24: "fr24_track_blocked_paused",
  request_in_progress: "fr24_track_blocked_progress",
};

function trackPanelRefs() {
  return {
    panel: $("#event-track-panel"),
    costLine: $("#event-track-cost"),
    button: $("#event-track-fetch"),
    result: $("#event-track-result"),
  };
}

async function setupEventTrackPanel(event) {
  // Pure state-setter: current event id and credit estimate travel via the
  // persistent panel's data attributes. The ONE click handler lives at
  // module init (delegated on the panel) -- a per-render addEventListener
  // here would accumulate handlers and stale event closures across views.
  const { panel, costLine, button, result } = trackPanelRefs();
  if (!panel || !costLine || !button || !result) return;
  panel.dataset.eventId = event.id;
  delete panel.dataset.credits;
  button.hidden = false;
  button.disabled = true; // blocked/unknown states show a disabled action (B3)
  costLine.textContent = "";
  result.textContent = "";
  let status;
  try {
    status = await api(`/api/fr24/events/${encodeURIComponent(event.id)}/track`);
  } catch {
    panel.hidden = true; // no authenticated view of this event's track state
    return;
  }
  panel.hidden = false;
  if (!status.available) {
    const key = TRACK_BLOCKED_KEYS[status.blocked_reason];
    costLine.textContent = key ? t(key) : t("fr24_track_loading");
    return; // button stays visible but disabled while blocked/fetched/paused
  }
  const creditsLabel = String(status.estimated_credits);
  panel.dataset.credits = creditsLabel;
  costLine.textContent = t("fr24_track_cost").replace("{credits}", creditsLabel);
  button.disabled = false;
}

function handleHashRoute() {
  const hash = window.location.hash || "";
  const match = hash.match(/^#\/events\/([a-f0-9-]+)$/i);
  if (match) {
    $$(".tab").forEach((t) => t.classList.remove("active"));
    $$(".view").forEach((v) => v.classList.remove("active"));
    const detailView = $("#view-event-detail");
    if (detailView) {
      detailView.classList.add("active");
      loadEventDetail(match[1]);
    }
  }
}

async function loadStatus() {
  const status = await api("/api/status");
  $("#phase-badge").textContent = status.phase;
  $("#warnings").innerHTML = status.warnings
    .map((warning) => `<div class="warning">${escapeHtml(warning)}</div>`)
    .join("");
  $("#metrics").innerHTML = [
    metric(t("metric_areas"), status.areas.selected, `${status.areas.total} ${t("metric_downloaded")}`),
    metric(t("metric_regions"), status.query_regions, `${status.estimated_requests_per_day} ${t("metric_estimated")}`),
    metric(t("metric_events"), status.events.total, `${status.events.review.useful || 0} ${t("metric_reviewed")}`),
    metric(t("metric_last_poll"), status.latest_poll?.success ? t("metric_healthy") : t("metric_not_ready"), status.latest_poll?.completed_at || t("metric_no_poll")),
  ].join("");
  const recent = await api("/api/events?limit=20");
  $("#dashboard-events").innerHTML = recent.events.length
    ? recent.events.map(eventRow).join("")
    : `<tr><td colspan="7" class="muted">${t("no_events")}</td></tr>`;
}

async function loadAreas() {
  const params = new URLSearchParams({ ...appState.areaFilter, limit: "500" });
  const result = await api(`/api/areas?${params}`);
  appState.areas = result.items;
  $("#area-summary").textContent = `${result.total} ${t("areas_matching")}`;
  $("#areas-body").innerHTML = result.items.length
    ? result.items
        .map(
          (area) => `<tr>
            <td><input class="area-checkbox" type="checkbox" data-id="${escapeHtml(area.id)}" ${area.selected ? "checked" : ""}></td>
            <td>${escapeHtml(area.name)}</td><td>${translateCategory(area.category)}</td>
            <td>${escapeHtml(area.state || "—")}</td><td>${escapeHtml(area.phase || "—")}</td>
            <td>${escapeHtml(area.source)}</td>
          </tr>`,
        )
        .join("")
    : `<tr><td colspan="6" class="muted">${t("areas_no_data")}</td></tr>`;
  $$(".area-checkbox").forEach((checkbox) => {
    checkbox.addEventListener("change", async () => {
      await api("/api/areas/selection", {
        method: "POST",
        body: JSON.stringify({ ids: [checkbox.dataset.id], selected: checkbox.checked }),
      });
      await loadStatus();
    });
  });
}

async function bulkVisible(selected) {
  const ids = $$(".area-checkbox").map((box) => box.dataset.id);
  if (!ids.length) return;
  await api("/api/areas/selection", { method: "POST", body: JSON.stringify({ ids, selected }) });
  await Promise.all([loadAreas(), loadStatus()]);
}

async function bulkFiltered(selected) {
  await api("/api/areas/selection", {
    method: "POST",
    body: JSON.stringify({ ...appState.areaFilter, selected }),
  });
  await Promise.all([loadAreas(), loadStatus()]);
}

function reviewCard(event) {
  const hexLinks = aircraftHexLinks(event.aircraft_hex);
  const hexDisplay = hexLinks.length
    ? `<a href="${hexLinks[0].url}" target="_blank" rel="noopener noreferrer" style="color:var(--ink);text-decoration:underline">${escapeHtml(event.aircraft_hex.toUpperCase())}</a>`
    : escapeHtml(event.aircraft_hex.toUpperCase());
  const regLinks = registrationLinks(event.registration);
  const regDisplay = event.registration
    ? (regLinks.length ? `<a href="${regLinks[0].url}" target="_blank" rel="noopener noreferrer" class="link-forest">${escapeHtml(event.registration)}</a>` : escapeHtml(event.registration))
    : "—";
  return `<article class="review-card" data-id="${escapeHtml(event.id)}">
    <div><strong>${eventLabel(event.event_type)} · ${hexDisplay}</strong> · ${regDisplay}<p>${escapeHtml(event.reason)}</p><p class="muted">${event.area_names.map(escapeHtml).join(", ")} · ${formatTime(event.occurred_at)}</p></div>
    <label>${t("col_review")}<select class="review-status"><option value="unreviewed">${t("review_unreviewed")}</option><option value="useful">${t("review_useful")}</option><option value="noise">${t("review_noise")}</option><option value="uncertain">${t("review_uncertain")}</option></select></label>
    <label>${t('review_notes')}<textarea class="review-notes" maxlength="4000">${escapeHtml(event.review_notes || "")}</textarea></label>
    <button class="button secondary review-save">${t("review_save")}</button>
  </article>`;
}

async function loadReviews() {
  const filter = $("#review-filter").value;
  const result = await api(`/api/events?limit=200&review_status=${encodeURIComponent(filter)}`);
  appState.events = result.events;
  $("#review-list").innerHTML = result.events.length
    ? result.events.map(reviewCard).join("")
    : `<p class="muted">${t("review_no_events")}</p>`;
  $$(".review-card").forEach((card, index) => {
    card.querySelector(".review-status").value = result.events[index].review_status;
    card.querySelector(".review-save").addEventListener("click", async () => {
      await api(`/api/events/${card.dataset.id}/review`, {
        method: "POST",
        body: JSON.stringify({
          status: card.querySelector(".review-status").value,
          notes: card.querySelector(".review-notes").value,
        }),
      });
      await loadStatus();
    });
  });
}

function formPayload(form) {
  const payload = {};
  [...form.elements].forEach((field) => {
    if (!field.name || field.disabled || field.name === "flight_providers") return;
    if (field.type === "checkbox") {
      payload[field.name] = field.checked;
    } else if (field.type === "number") {
      payload[field.name] = Number(field.value);
    } else {
      payload[field.name] = field.value;
    }
  });
  return payload;
}

async function saveForm(form, override = null) {
  const resultBox = form.querySelector(".form-result");
  const values = override || formPayload(form);
  try {
    const result = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify({ values }),
    });
    if (Object.keys(result.errors).length) {
      resultBox.textContent = Object.entries(result.errors).map(([key, value]) => `${key}: ${value}`).join(" · ");
    } else {
      resultBox.textContent = t("settings_saved");
    }
    await Promise.all([loadSettings(), loadStatus()]);
  } catch (error) {
    resultBox.textContent = error.message;
  }
}

function setField(form, key, setting) {
  const field = form.elements.namedItem(key);
  if (!field) return;
  if (field instanceof RadioNodeList) return;
  if (field.type === "checkbox" && !setting.secret) {
    field.checked = Boolean(setting.value);
  } else if (!setting.secret && setting.value !== null) {
    field.value = setting.value;
  }
  field.disabled = Boolean(setting.locked);
  if (setting.locked) field.title = t("env_controlled");
}

function applyTranslations() {
  // Navigation
  $$("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (el.placeholder !== undefined && el.tagName === "INPUT") {
      el.placeholder = t(key);
    } else if (el.tagName === "LABEL" && (el.querySelector("input") || el.querySelector("select"))) {
      // For labels containing form controls, only translate the first text node
      const textNode = Array.from(el.childNodes).find(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
      if (textNode) {
        textNode.textContent = t(key) + " ";
      }
    } else if (key === "login_subtitle") {
      // Special handling for login subtitle to preserve <code>ADMIN_PASSWORD</code>
      el.textContent = t(key) + " ";
      const code = document.createElement("code");
      code.textContent = "ADMIN_PASSWORD";
      el.appendChild(code);
      el.appendChild(document.createTextNode("."));
    } else {
      el.textContent = t(key);
    }
  });
  // Update HTML lang attribute
  updateHtmlLang();
  // Update language toggle button
  const langBtn = $("#lang-toggle");
  if (langBtn) langBtn.textContent = appState.language === "pt" ? "PT" : "EN";
  // Update language selector
  const langSelect = $("#settings-language");
  if (langSelect) langSelect.value = appState.language;
  // Update timezone selector
  const tzSelect = $("#settings-timezone");
  if (tzSelect) tzSelect.value = appState.timezone;
}

async function loadSettings() {
  const result = await api("/api/settings");
  appState.settings = result.settings;
  const settings = result.settings;

  // Apply language and timezone from settings
  if (settings.language && settings.language.value) {
    appState.language = settings.language.value;
  }
  if (settings.timezone && settings.timezone.value) {
    appState.timezone = settings.timezone.value;
  }

  ["settings-core", "settings-email", "settings-thresholds", "settings-display", "fr24-budget-policy-form"].forEach((id) => {
    const form = $(`#${id}`);
    if (form) {
      Object.entries(settings).forEach(([key, setting]) => setField(form, key, setting));
    }
  });
  $$("input[name='flight_providers']").forEach((box) => {
    box.checked = settings.flight_providers.value.includes(box.value);
    box.disabled = settings.flight_providers.locked;
  });
  $("#provider-tests").innerHTML = Object.entries(result.provider_options)
    .map(([id, info]) => `<div class="provider-test"><div><strong>${escapeHtml(info.name)}</strong><p>${escapeHtml(info.note)}</p></div><button class="button secondary" data-provider="${id}">${t('test_button')}</button><span></span></div>`)
    .join("");
  $$("button[data-provider]").forEach((button) => {
    button.addEventListener("click", async () => {
      const output = button.nextElementSibling;
      output.textContent = t("settings_testing");
      try {
        const response = await api(`/api/providers/${button.dataset.provider}/test`, { method: "POST" });
        output.textContent = `${response.aircraft} ${t("settings_aircraft_returned")}`;
      } catch (error) {
        output.textContent = error.message;
      }
    });
  });

  applyTranslations();
}

async function runAction(button, text, endpoint) {
  const output = $("#action-result");
  button.disabled = true;
  output.textContent = text;
  try {
    const response = await api(endpoint, { method: "POST" });
    output.textContent = response.error_message || response.error || response.status || t("action_completed");
    await Promise.all([loadStatus(), loadSettings()]);
  } catch (error) {
    output.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function init() {
  appState.language = detectBrowserLanguage();
  updateHtmlLang();
  // Fetch translations from backend (single source of truth)
  try {
    const i18n = await fetch("/api/i18n", { credentials: "same-origin" });
    if (i18n.ok) appState.translations = await i18n.json();
  } catch { /* fallbackTranslations stays in use */ }
  const auth = await api("/api/auth/status");
  if (!auth.authenticated) return showLogin();
  appState.csrfToken = auth.csrf_token;
  showApp();
  await Promise.all([loadStatus(), loadSettings()]);
  handleHashRoute();
}

window.addEventListener("hashchange", handleHashRoute);

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const response = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ password: $("#login-password").value }),
    });
    appState.csrfToken = response.csrf_token;
    $("#login-error").textContent = "";
    showApp();
    await Promise.all([loadStatus(), loadSettings()]);
  } catch (error) {
    $("#login-error").textContent = error.message;
  }
});

$("#logout").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  showLogin();
});

$("#lang-toggle").addEventListener("click", async () => {
  appState.language = appState.language === "pt" ? "en" : "pt";
  $("#lang-toggle").textContent = appState.language === "pt" ? "PT" : "EN";
  updateHtmlLang();
  applyTranslations();
  // Re-render the active data view so table rows pick up the new language
  const activeTab = $(".tab.active");
  if (activeTab) {
    const view = activeTab.dataset.view;
    if (view === "dashboard") await loadStatus();
    if (view === "areas") await loadAreas();
    if (view === "events") await loadReviews();
    if (view === "settings") await loadSettings();
    if (view === "fr24") await loadFr24();
  }
  if (appState.csrfToken) {
    try {
      await api("/api/settings", { method: "POST", body: JSON.stringify({ values: { language: appState.language } }) });
    } catch { /* best effort */ }
  }
});

$$(".tab").forEach((tab) => {
  tab.addEventListener("click", async () => {
    $$(".tab").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    $$(".view").forEach((view) => view.classList.remove("active"));
    $(`#view-${tab.dataset.view}`).classList.add("active");
    if (tab.dataset.view === "areas") await loadAreas();
    if (tab.dataset.view === "events") await loadReviews();
    if (tab.dataset.view === "settings") await loadSettings();
    if (tab.dataset.view === "fr24") await loadFr24();
  });
});

$("#sync-now").addEventListener("click", (event) => runAction(event.currentTarget, t("action_syncing"), "/api/boundaries/sync"));
$("#poll-now").addEventListener("click", (event) => runAction(event.currentTarget, t("action_polling"), "/api/poll"));
$("#test-email").addEventListener("click", (event) => runAction(event.currentTarget, t("action_testing_email"), "/api/email/test"));
$("#refresh").addEventListener("click", loadStatus);
$("#area-filter").addEventListener("click", () => {
  appState.areaFilter = { search: $("#area-search").value, category: $("#area-category").value, selected: $("#area-selected").value };
  loadAreas();
});
$("#select-visible").addEventListener("click", () => bulkVisible(true));
$("#deselect-visible").addEventListener("click", () => bulkVisible(false));
$("#select-all-filtered").addEventListener("click", () => bulkFiltered(true));
$("#review-refresh").addEventListener("click", loadReviews);
$("#settings-core").addEventListener("submit", (event) => {
  event.preventDefault();
  saveForm(event.currentTarget, { ...formPayload(event.currentTarget), flight_providers: $$("input[name='flight_providers']:checked").map((box) => box.value) });
});
$("#settings-keys").addEventListener("submit", (event) => { event.preventDefault(); saveForm(event.currentTarget); });
$("#settings-email").addEventListener("submit", (event) => {
  event.preventDefault();
  const payload = formPayload(event.currentTarget);
  payload.alert_recipients = payload.alert_recipients.split(",").map((item) => item.trim()).filter(Boolean);
  saveForm(event.currentTarget, payload);
});
$("#settings-thresholds").addEventListener("submit", (event) => { event.preventDefault(); saveForm(event.currentTarget); });
$("#settings-display")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const payload = formPayload(event.currentTarget);
  saveForm(event.currentTarget, payload);
});

$("#fr24-manual-bounds")?.addEventListener("change", (event) => {
  $("#fr24-manual-bounds-fields").hidden = !event.currentTarget.checked;
});

$("#fr24-enable-toggle")?.addEventListener("change", async (event) => {
  // FR24_ENABLED kill switch. Saved through the generic settings endpoint,
  // which rejects the write when the value is pinned by the environment --
  // the checkbox is already disabled in that case, so this catch is just a
  // safety net that reports the reason instead of failing silently.
  try {
    await api("/api/settings", {
      method: "POST",
      body: JSON.stringify({ values: { fr24_enabled: event.currentTarget.checked } }),
    });
  } catch (error) {
    window.alert(error.message);
  }
  await loadFr24();
});
$("#fr24-budget-policy-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  // Generic settings POST machinery; then reload the FR24 tab so the
  // current/effect/source lines re-render from the server's answer.
  await saveForm(event.currentTarget);
  await loadFr24();
});

$("#fr24-cluster-reset")?.addEventListener("click", fr24ResetForm);

$("#fr24-cluster-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const resultBox = form.querySelector(".form-result");
  const payload = {
    id: form.elements.namedItem("id").value || null,
    name: form.elements.namedItem("name").value,
    enabled: form.elements.namedItem("enabled").checked,
    buffer_km: Number(form.elements.namedItem("buffer_km").value),
    min_altitude_ft: Number(form.elements.namedItem("min_altitude_ft").value),
    max_altitude_ft: Number(form.elements.namedItem("max_altitude_ft").value),
    categories: $$("input[name='categories']:checked").map((box) => box.value),
    area_ids: $$(".fr24-area-checkbox:checked").map((box) => box.value),
    use_manual_bounds: form.elements.namedItem("use_manual_bounds").checked,
    manual_north: form.elements.namedItem("manual_north").value
      ? Number(form.elements.namedItem("manual_north").value)
      : null,
    manual_south: form.elements.namedItem("manual_south").value
      ? Number(form.elements.namedItem("manual_south").value)
      : null,
    manual_west: form.elements.namedItem("manual_west").value
      ? Number(form.elements.namedItem("manual_west").value)
      : null,
    manual_east: form.elements.namedItem("manual_east").value
      ? Number(form.elements.namedItem("manual_east").value)
      : null,
  };
  try {
    await api("/api/fr24/clusters", { method: "POST", body: JSON.stringify(payload) });
    resultBox.textContent = t("settings_saved");
    fr24ResetForm();
    await loadFr24();
  } catch (error) {
    resultBox.textContent = error.message;
  }
});

$("#fr24-test")?.addEventListener("click", async (event) => {
  // This is a paid, real FR24 call -- disable the button for the duration
  // so a double-click (or an impatient repeat click while the first request
  // is still in flight) can't trigger two billed requests.
  const button = event.currentTarget;
  const resultBox = $("#fr24-test-result");
  button.disabled = true;
  resultBox.textContent = t("fr24_testing");
  try {
    const result = await api("/api/fr24/test", { method: "POST" });
    resultBox.textContent = `${t("fr24_test_success")}: ${result.aircraft_found} ${t("fr24_aircraft_found")}, ${result.estimated_credits} ${t("fr24_credits")}`;
  } catch (error) {
    resultBox.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

// B2: the #event-track-panel persists in index.html, so its click handling is
// registered EXACTLY ONCE here (delegated) instead of per event-detail render.
// The handler reads the CURRENT event id / credit estimate from the panel's
// dataset at click time -- stale closures across events are impossible.
$("#event-track-panel")?.addEventListener("click", async (event) => {
  const button = event.target.closest("#event-track-fetch");
  if (!button || button.disabled || button.hidden) return;
  const panel = event.currentTarget;
  const eventId = panel.dataset.eventId;
  if (!eventId) return;
  if (!window.confirm(t("fr24_track_confirm").replace("{credits}", panel.dataset.credits || ""))) return;
  button.disabled = true;
  const resultBox = $("#event-track-result");
  if (resultBox) resultBox.textContent = t("fr24_track_fetching");
  try {
    const done = await api(`/api/fr24/events/${encodeURIComponent(eventId)}/track`, {
      method: "POST",
      body: JSON.stringify({ confirm: true }),
    });
    await loadEventDetail(eventId); // rerender; status flips to already_fetched
    // B3: flash AFTER the reload so fr24_track_success is actually consumed
    // and visible next to the now-disabled button.
    const refs = $("#event-track-result");
    if (refs) {
      refs.textContent = t("fr24_track_success")
        .replace("{records}", String(done.records_returned ?? ""))
        .replace("{credits}", String(done.estimated_credits ?? ""));
    }
  } catch (error) {
    const detail = String(error.message || "");
    let message = TRACK_BLOCKED_KEYS[detail] ? t(TRACK_BLOCKED_KEYS[detail]) : "";
    if (!message && detail.includes("pause_fr24")) message = t("fr24_track_blocked_paused");
    if (resultBox) resultBox.textContent = message || t("fr24_track_error").replace("{detail}", detail);
    button.disabled = false;
  }
});

init().catch((error) => {
  $("#login-error").textContent = error.message;
  showLogin();
});
