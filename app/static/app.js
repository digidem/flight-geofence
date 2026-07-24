// Portuguese translations (default)
const translations = {
  pt: {
    nav_dashboard: "Painel",
    nav_areas: "Áreas protegidas",
    nav_events: "Revisar eventos",
    nav_settings: "Configurações",
    login_title: "Interface de monitoramento protegida",
    login_subtitle: "Use a senha configurada como",
    login_button: "Entrar",
    login_password_label: "Senha",
    logout_button: "Sair",
    phase_shadow: "Sombra",
    phase_review: "Revisão",
    phase_live: "Ao vivo",
    dashboard_subtitle: "Monitoramento territorial · PoC com dados reais",
    dashboard_current_phase: "Fase atual",
    dashboard_three_phase: "Fluxo de três fases",
    shadow_desc: "APIs oficiais e limites oficiais. Eventos são armazenados, mas nenhum alerta externo é enviado.",
    review_desc: "Classifique eventos como úteis, ruído ou incerto e ajuste limiares e áreas selecionadas.",
    live_desc: "Apenas eventos de pouso provável e desaparecimento acionam a entrega de e-mail configurada.",
    dashboard_actions: "Ações",
    dashboard_operations: "Operações",
    sync_boundaries: "Sincronizar limites oficiais",
    run_poll: "Executar consulta de voo agora",
    test_email: "Testar entrega de e-mail",
    refresh_status: "Atualizar status",
    action_syncing: "Baixando e processando limites oficiais…",
    action_polling: "Consultando fornecedores de voo…",
    action_testing_email: "Testando entrega de e-mail…",
    dashboard_recent: "Sinais recentes",
    dashboard_events: "Eventos suspeitos",
    no_events: "Nenhum evento suspeito ainda.",
    metric_areas: "Áreas protegidas",
    metric_regions: "Regiões de consulta",
    metric_events: "Eventos",
    metric_last_poll: "Última consulta",
    metric_healthy: "Saudável",
    metric_not_ready: "Não pronto",
    metric_no_poll: "Nenhuma consulta ainda",
    metric_reviewed: "revisados úteis",
    metric_estimated: "requisições estimadas/dia",
    metric_downloaded: "baixados",
    col_time: "Horário",
    col_signal: "Sinal",
    col_aircraft: "Aeronave",
    col_areas: "Áreas",
    col_telemetry: "Telemetria",
    col_phase: "Fase",
    col_review: "Revisão",
    signal_stop: "Possível pouso",
    signal_disappeared: "Desapareceu",
    event_probable_stop: "Possível Pouso",
    event_disappearance: "Desaparecimento",
    class_scheduled_airline: "Companhia aérea",
    class_unknown_candidate: "Candidato desconhecido",
    class_non_airline_candidate: "Candidato não-companhia",
    category_indigenous_territory: "Território indígena",
    category_conservation_unit: "Unidade de conservação",
    areas_subtitle: "Dados oficiais FUNAI + CNUC",
    areas_title: "Selecionar áreas monitoradas",
    areas_search: "Buscar nome, estado ou fase",
    areas_all_types: "Todos os tipos",
    areas_indigenous: "Territórios indígenas",
    areas_conservation: "Unidades de conservação",
    areas_all: "Todos",
    areas_selected: "Selecionados",
    areas_not_selected: "Não selecionados",
    areas_filter: "Filtrar",
    areas_select_visible: "Selecionar visíveis",
    areas_deselect_visible: "Desselecionar visíveis",
    areas_select_filtered: "Selecionar todos filtrados",
    areas_matching: "áreas correspondentes",
    col_monitor: "Monitorar",
    col_name: "Nome",
    col_type: "Tipo",
    col_state: "Estado",
    col_phase_category: "Fase/Categoria",
    col_source: "Fonte",
    areas_no_data: "Nenhuma área encontrada. Execute a sincronização de limites primeiro.",
    review_subtitle: "Evidência de calibração",
    review_title: "Revisar eventos detectados",
    review_all: "Todas as revisões",
    review_unreviewed: "Não revisados",
    review_useful: "Úteis",
    review_noise: "Ruído",
    review_uncertain: "Incertos",
    review_refresh: "Atualizar",
    review_save: "Salvar revisão",
    review_no_events: "Nenhum evento correspondente.",
    settings_workflow: "Fluxo de trabalho",
    settings_phase_providers: "Fase e fornecedores",
    settings_operating_phase: "Fase operacional",
    settings_flight_providers: "Fornecedores de voo",
    settings_poll_interval: "Intervalo de consulta (segundos)",
    settings_save_workflow: "Salvar fluxo de trabalho",
    settings_saved: "Salvo.",
    settings_secrets: "Segredos",
    settings_api_keys: "Chaves de API",
    settings_fr24_key: "Token Flightradar24",
    settings_adsb_key: "Chave ADS-B Exchange",
    settings_resend_key: "Chave API Resend",
    settings_placeholder: "Deixe em branco para manter existente",
    settings_save_keys: "Salvar chaves com segurança",
    settings_notifications: "Notificações",
    settings_email: "E-mail",
    settings_email_provider: "Provedor de e-mail",
    settings_console: "Pré-visualização no console",
    settings_recipients: "Destinatários, separados por vírgula",
    settings_sender: "Remetente",
    settings_smtp_host: "Host SMTP",
    settings_smtp_port: "Porta SMTP",
    settings_smtp_user: "Usuário SMTP",
    settings_smtp_pass: "Senha SMTP",
    settings_smtp_starttls: "Usar STARTTLS",
    settings_save_email: "Salvar configurações de e-mail",
    settings_detection: "Detecção",
    settings_noise: "Controles de ruído",
    settings_stop_obs: "Observações para pouso",
    settings_stop_duration: "Duração mínima do pouso (segundos)",
    settings_stationary_radius: "Raio estacionário (metros)",
    settings_max_stop_speed: "Velocidade máxima de pouso (kt)",
    settings_disappear_obs: "Observações para desaparecimento",
    settings_disappear_polls: "Pollings bem-sucedidos para desaparecimento",
    settings_disappear_alt: "Altitude máxima de desaparecimento (ft)",
    settings_outside_obs: "Observações externas para fechar episódio",
    settings_max_emails: "Limite diário de e-mails",
    settings_save_thresholds: "Salvar limiares",
    settings_connectivity: "Conectividade",
    settings_test_providers: "Testar fornecedores",
    settings_testing: "Testando…",
    settings_aircraft_returned: "aeronaves retornadas",
    settings_timezone: "Fuso horário",
    timezone_label: "Fuso horário do painel",
    settings_language: "Idioma",
    settings_display: "Exibição",
    time_at: " às ",
  },
  en: {
    nav_dashboard: "Dashboard",
    nav_areas: "Protected areas",
    nav_events: "Review events",
    nav_settings: "Settings",
    login_title: "Protected monitoring interface",
    login_subtitle: "Use the password configured as",
    login_button: "Log in",
    login_password_label: "Password",
    logout_button: "Log out",
    phase_shadow: "Shadow",
    phase_review: "Review",
    phase_live: "Live",
    dashboard_subtitle: "Territorial monitoring · real-data PoC",
    dashboard_current_phase: "Current phase",
    dashboard_three_phase: "Three-phase workflow",
    shadow_desc: "Real APIs and official boundaries. Events are stored, but no external alert is sent.",
    review_desc: "Classify events as useful, noise, or uncertain and adjust thresholds and selected areas.",
    live_desc: "Only probable landing and disappearance events trigger configured email delivery.",
    dashboard_actions: "Actions",
    dashboard_operations: "Operations",
    sync_boundaries: "Sync official boundaries",
    run_poll: "Run flight poll now",
    test_email: "Test email delivery",
    refresh_status: "Refresh status",
    action_syncing: "Downloading and processing official boundaries…",
    action_polling: "Polling flight providers…",
    action_testing_email: "Testing email delivery…",
    dashboard_recent: "Recent signals",
    dashboard_events: "Suspicious events",
    no_events: "No suspicious events yet.",
    metric_areas: "Protected areas",
    metric_regions: "Query regions",
    metric_events: "Events",
    metric_last_poll: "Last poll",
    metric_healthy: "Healthy",
    metric_not_ready: "Not ready",
    metric_no_poll: "No poll yet",
    metric_reviewed: "reviewed useful",
    metric_estimated: "estimated requests/day",
    metric_downloaded: "downloaded",
    col_time: "Time",
    col_signal: "Signal",
    col_aircraft: "Aircraft",
    col_areas: "Areas",
    col_telemetry: "Telemetry",
    col_phase: "Phase",
    col_review: "Review",
    signal_stop: "Possible landing",
    signal_disappeared: "Disappeared",
    event_probable_stop: "Possible Landing",
    event_disappearance: "Disappearance",
    class_scheduled_airline: "Scheduled airline",
    class_unknown_candidate: "Unknown candidate",
    class_non_airline_candidate: "Non-airline candidate",
    category_indigenous_territory: "Indigenous territory",
    category_conservation_unit: "Conservation unit",
    areas_subtitle: "Official FUNAI + CNUC data",
    areas_title: "Select monitored areas",
    areas_search: "Search name, state or phase",
    areas_all_types: "All types",
    areas_indigenous: "Indigenous territories",
    areas_conservation: "Conservation units",
    areas_all: "All",
    areas_selected: "Selected",
    areas_not_selected: "Not selected",
    areas_filter: "Filter",
    areas_select_visible: "Select visible",
    areas_deselect_visible: "Deselect visible",
    areas_select_filtered: "Select all filtered",
    areas_matching: "matching areas",
    col_monitor: "Monitor",
    col_name: "Name",
    col_type: "Type",
    col_state: "State",
    col_phase_category: "Phase/category",
    col_source: "Source",
    areas_no_data: "No areas found. Run boundary synchronization first.",
    review_subtitle: "Calibration evidence",
    review_title: "Review detected events",
    review_all: "All reviews",
    review_unreviewed: "Unreviewed",
    review_useful: "Useful",
    review_noise: "Noise",
    review_uncertain: "Uncertain",
    review_refresh: "Refresh",
    review_save: "Save review",
    review_no_events: "No matching events.",
    settings_workflow: "Workflow",
    settings_phase_providers: "Phase and providers",
    settings_operating_phase: "Operating phase",
    settings_flight_providers: "Flight providers",
    settings_poll_interval: "Poll interval (seconds)",
    settings_save_workflow: "Save workflow",
    settings_saved: "Saved.",
    settings_secrets: "Secrets",
    settings_api_keys: "API keys",
    settings_fr24_key: "Flightradar24 token",
    settings_adsb_key: "ADS-B Exchange key",
    settings_resend_key: "Resend API key",
    settings_placeholder: "Leave blank to keep existing",
    settings_save_keys: "Save keys securely",
    settings_notifications: "Notifications",
    settings_email: "Email",
    settings_email_provider: "Email provider",
    settings_console: "Console preview",
    settings_recipients: "Recipients, comma-separated",
    settings_sender: "Sender",
    settings_smtp_host: "SMTP host",
    settings_smtp_port: "SMTP port",
    settings_smtp_user: "SMTP username",
    settings_smtp_pass: "SMTP password",
    settings_smtp_starttls: "Use STARTTLS",
    settings_save_email: "Save email settings",
    settings_detection: "Detection",
    settings_noise: "Noise controls",
    settings_stop_obs: "Stop observations",
    settings_stop_duration: "Stop duration seconds",
    settings_stationary_radius: "Stationary radius metres",
    settings_max_stop_speed: "Maximum stop speed kt",
    settings_disappear_obs: "Disappearance observations",
    settings_disappear_polls: "Missing successful polls",
    settings_disappear_alt: "Maximum disappearance altitude ft",
    settings_outside_obs: "Outside observations to close episode",
    settings_max_emails: "Daily email cap",
    settings_save_thresholds: "Save thresholds",
    settings_connectivity: "Connectivity",
    settings_test_providers: "Test providers",
    settings_testing: "Testing…",
    settings_aircraft_returned: "aircraft returned",
    settings_timezone: "Timezone",
    timezone_label: "Dashboard timezone",
    settings_language: "Language",
    settings_display: "Display",
    time_at: " at ",
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
  return (translations[lang] && translations[lang][key]) || translations.en[key] || key;
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

function aircraftUrl(hex) {
  return `https://www.flightradar24.com/data/aircraft/${hex.toLowerCase()}`;
}

function aircraftTypeUrl(type) {
  return type ? `https://www.flightradar24.com/data/aircraft/${type.toLowerCase()}` : null;
}

function registrationUrl(registration) {
  if (!registration) return null;
  const reg = registration.toUpperCase().replace(/-/g, "");
  // For Brazilian registrations (PT-XXX), link to ANAC SIGA
  if (reg.startsWith("PT")) {
    return `https://www.gov.br/anac/pt-br/assuntos/registro-aeronaves`;
  }
  // For other registrations, link to FlightRadar24
  return `https://www.flightradar24.com/data/aircraft/${reg.toLowerCase()}`;
}

function eventRow(event) {
  const hex = event.aircraft_hex.toUpperCase();
  const typeUrl = aircraftTypeUrl(event.aircraft_type);
  const typeDisplay = event.aircraft_type
    ? (typeUrl ? `<a href="${typeUrl}" target="_blank" rel="noopener" style="color:var(--forest);text-decoration:underline">${escapeHtml(event.aircraft_type)}</a>` : escapeHtml(event.aircraft_type))
    : "—";
  const regUrl = registrationUrl(event.registration);
  const regDisplay = event.registration
    ? (regUrl ? `<a href="${regUrl}" target="_blank" rel="noopener" style="color:var(--forest);text-decoration:underline">${escapeHtml(event.registration)}</a>` : escapeHtml(event.registration))
    : "—";
  return `<tr>
    <td>${formatTime(event.occurred_at)}</td>
    <td><span class="signal ${event.event_type === "PROBABLE_STOP" ? "stop" : "disappeared"}">${eventLabel(event.event_type)}</span></td>
    <td><strong><a href="${aircraftUrl(event.aircraft_hex)}" target="_blank" rel="noopener" style="color:var(--ink);text-decoration:underline">${escapeHtml(hex)}</a></strong><div class="muted">${escapeHtml(event.callsign || "—")} · ${regDisplay} · ${typeDisplay}</div></td>
    <td>${event.area_names.map(escapeHtml).join("<br>")}</td>
    <td>${escapeHtml(String(event.altitude_ft ?? "—"))} ft · ${escapeHtml(String(event.ground_speed_kt ?? "—"))} kt</td>
    <td>${escapeHtml(event.phase)}</td>
    <td>${escapeHtml(event.review_status)}</td>
  </tr>`;
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
  const regUrl = registrationUrl(event.registration);
  const regDisplay = event.registration
    ? (regUrl ? `<a href="${regUrl}" target="_blank" rel="noopener" style="color:var(--forest);text-decoration:underline">${escapeHtml(event.registration)}</a>` : escapeHtml(event.registration))
    : "—";
  return `<article class="review-card" data-id="${escapeHtml(event.id)}">
    <div><strong>${eventLabel(event.event_type)} · <a href="${aircraftUrl(event.aircraft_hex)}" target="_blank" rel="noopener" style="color:var(--ink);text-decoration:underline">${escapeHtml(event.aircraft_hex.toUpperCase())}</a></strong> · ${regDisplay}<p>${escapeHtml(event.reason)}</p><p class="muted">${event.area_names.map(escapeHtml).join(", ")} · ${formatTime(event.occurred_at)}</p></div>
    <label>${t("col_review")}<select class="review-status"><option value="unreviewed">${t("review_unreviewed")}</option><option value="useful">${t("review_useful")}</option><option value="noise">${t("review_noise")}</option><option value="uncertain">${t("review_uncertain")}</option></select></label>
    <label>Notes<textarea class="review-notes" maxlength="4000">${escapeHtml(event.review_notes || "")}</textarea></label>
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
  if (setting.locked) field.title = "Controlled by environment variable";
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

  ["settings-core", "settings-email", "settings-thresholds", "settings-display"].forEach((id) => {
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
    .map(([id, info]) => `<div class="provider-test"><div><strong>${escapeHtml(info.name)}</strong><p>${escapeHtml(info.note)}</p></div><button class="button secondary" data-provider="${id}">Test</button><span></span></div>`)
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
    output.textContent = response.error_message || response.error || response.status || "Completed.";
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
  const auth = await api("/api/auth/status");
  if (!auth.authenticated) return showLogin();
  appState.csrfToken = auth.csrf_token;
  showApp();
  await Promise.all([loadStatus(), loadSettings()]);
}

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

$$(".tab").forEach((tab) => {
  tab.addEventListener("click", async () => {
    $$(".tab").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    $$(".view").forEach((view) => view.classList.remove("active"));
    $(`#view-${tab.dataset.view}`).classList.add("active");
    if (tab.dataset.view === "areas") await loadAreas();
    if (tab.dataset.view === "events") await loadReviews();
    if (tab.dataset.view === "settings") await loadSettings();
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

init().catch((error) => {
  $("#login-error").textContent = error.message;
  showLogin();
});
