"""Internationalization support for Flight Geofence Alerts."""

TRANSLATIONS = {
    "pt": {
        # Event types
        "event_probable_stop": "Possível Pouso",
        "event_disappearance": "Desaparecimento",
        # Aircraft classifications
        "class_scheduled_airline": "Companhia aérea",
        "class_unknown_candidate": "Candidato desconhecido",
        "class_non_airline_candidate": "Candidato não-companhia",
        # Phase names
        "phase_shadow": "Sombra",
        "phase_review": "Revisão",
        "phase_live": "Ao vivo",
        # Review statuses
        "review_unreviewed": "Não revisado",
        "review_useful": "Útil",
        "review_noise": "Ruído",
        "review_uncertain": "Incerto",
        # Area categories
        "category_indigenous_territory": "Território indígena",
        "category_conservation_unit": "Unidade de conservação",
        # Email
        "email_title": "Alerta de Vôo Suspeito",
        "email_event": "Evento",
        "email_aircraft": "Aeronave",
        "email_callsign": "Indicativo",
        "email_registration": "Registro",
        "email_aircraft_type": "Tipo de aeronave",
        "email_protected_areas": "Áreas protegidas",
        "email_time": "Horário",
        "email_last_position": "Última posição",
        "email_altitude": "Altitude",
        "email_ground_speed": "Velocidade",
        "email_provider": "Fonte",
        "email_source_type": "Tipo de dado",
        "email_origin": "Origem",
        "email_destination": "Destino",
        "email_reason": "Motivo",
        "email_classification": "Classificação",
        "email_disclaimer": "Este é um sinal de monitoramento não verificado. Não prova pouso, desligamento intencional de transponder, mineração ilegal ou irregularidade. Verifique com outras evidências antes de agir.",
        "email_possible_stop": "Possível pouso",
        "email_disappeared": "Posição da aeronave desapareceu",
        "email_unavailable": "Indisponível",
        "email_footer": "Alertas de Geovoo de Voo — Monitoramento territorial",
        # Dashboard
        "nav_dashboard": "Painel",
        "nav_areas": "Áreas protegidas",
        "nav_events": "Revisar eventos",
        "nav_settings": "Configurações",
        "login_title": "Interface de monitoramento protegida",
        "login_subtitle": "Use a senha configurada como",
        "login_button": "Entrar",
        "login_password_label": "Senha",
        "logout_button": "Sair",
        "phase_badge": "Fase",
        "dashboard_subtitle": "Monitoramento territorial · PoC com dados reais",
        "dashboard_current_phase": "Fase atual",
        "dashboard_three_phase": "Fluxo de três fases",
        "shadow_description": "APIs oficiais e limites oficiais. Eventos são armazenados, mas nenhum alerta externo é enviado.",
        "review_description": "Classifique eventos como úteis, ruído ou incerto e ajuste limiares e áreas selecionadas.",
        "live_description": "Apenas eventos de pouso provável e desaparecimento acionam a entrega de e-mail configurada.",
        "dashboard_actions": "Ações",
        "dashboard_operations": "Operações",
        "sync_boundaries": "Sincronizar limites oficiais",
        "run_poll": "Executar consulta de voo agora",
        "test_email": "Testar entrega de e-mail",
        "refresh_status": "Atualizar status",
        "action_syncing": "Baixando e processando limites oficiais…",
        "action_polling": "Consultando fornecedores de voo…",
        "action_testing_email": "Testando entrega de e-mail…",
        "dashboard_recent": "Sinais recentes",
        "dashboard_events": "Eventos suspeitos",
        "dashboard_no_events": "Nenhum evento suspeito ainda.",
        "metric_areas": "Áreas protegidas",
        "metric_regions": "Regiões de consulta",
        "metric_events": "Eventos",
        "metric_last_poll": "Última consulta",
        "metric_healthy": "Saudável",
        "metric_not_ready": "Não pronto",
        "metric_no_poll": "Nenhuma consulta ainda",
        "metric_reviewed": "revisados úteis",
        "metric_estimated": "requisições estimadas/dia",
        "metric_downloaded": "baixados",
        # Events table
        "col_time": "Horário",
        "col_signal": "Sinal",
        "col_aircraft": "Aeronave",
        "col_areas": "Áreas",
        "col_telemetry": "Telemetria",
        "col_phase": "Fase",
        "col_review": "Revisão",
        "signal_stop": "Possível pouso",
        "signal_disappeared": "Desapareceu",
        # Areas
        "areas_subtitle": "Dados oficiais FUNAI + CNUC",
        "areas_title": "Selecionar áreas monitoradas",
        "areas_search": "Buscar nome, estado ou fase",
        "areas_all_types": "Todos os tipos",
        "areas_indigenous": "Territórios indígenas",
        "areas_conservation": "Unidades de conservação",
        "areas_all": "Todos",
        "areas_selected": "Selecionados",
        "areas_not_selected": "Não selecionados",
        "areas_filter": "Filtrar",
        "areas_select_visible": "Selecionar visíveis",
        "areas_deselect_visible": "Desselecionar visíveis",
        "areas_select_filtered": "Selecionar todos filtrados",
        "areas_matching": "áreas correspondentes",
        "col_monitor": "Monitorar",
        "col_name": "Nome",
        "col_type": "Tipo",
        "col_state": "Estado",
        "col_phase_category": "Fase/Categoria",
        "col_source": "Fonte",
        "areas_no_data": "Nenhuma área encontrada. Execute a sincronização de limites primeiro.",
        # Events review
        "review_subtitle": "Evidência de calibração",
        "review_title": "Revisar eventos detectados",
        "review_all": "Todas as revisões",
        "review_refresh": "Atualizar",
        "review_save": "Salvar revisão",
        "review_no_events": "Nenhum evento correspondente.",
        # Settings
        "settings_workflow": "Fluxo de trabalho",
        "settings_phase_providers": "Fase e fornecedores",
        "settings_operating_phase": "Fase operacional",
        "settings_flight_providers": "Fornecedores de voo",
        "settings_poll_interval": "Intervalo de consulta (segundos)",
        "settings_save_workflow": "Salvar fluxo de trabalho",
        "settings_saved": "Salvo.",
        "settings_secrets": "Segredos",
        "settings_api_keys": "Chaves de API",
        "settings_fr24_key": "Token Flightradar24",
        "settings_adsb_key": "Chave ADS-B Exchange",
        "settings_resend_key": "Chave API Resend",
        "settings_placeholder": "Deixe em branco para manter existente",
        "settings_save_keys": "Salvar chaves com segurança",
        "settings_notifications": "Notificações",
        "settings_email": "E-mail",
        "settings_email_provider": "Provedor de e-mail",
        "settings_console": "Pré-visualização no console",
        "settings_recipients": "Destinatários, separados por vírgula",
        "settings_sender": "Remetente",
        "settings_smtp_host": "Host SMTP",
        "settings_smtp_port": "Porta SMTP",
        "settings_smtp_user": "Usuário SMTP",
        "settings_smtp_pass": "Senha SMTP",
        "settings_smtp_starttls": "Usar STARTTLS",
        "settings_save_email": "Salvar configurações de e-mail",
        "settings_detection": "Detecção",
        "settings_noise": "Controles de ruído",
        "settings_stop_obs": "Observações para pouso",
        "settings_stop_duration": "Duração mínima do pouso (segundos)",
        "settings_stationary_radius": "Raio estacionário (metros)",
        "settings_max_stop_speed": "Velocidade máxima de pouso (kt)",
        "settings_disappear_obs": "Observações para desaparecimento",
        "settings_disappear_polls": "Pollings bem-sucedidos para desaparecimento",
        "settings_disappear_alt": "Altitude máxima de desaparecimento (ft)",
        "settings_outside_obs": "Observações externas para fechar episódio",
        "settings_max_emails": "Limite diário de e-mails",
        "settings_save_thresholds": "Salvar limiares",
        "settings_connectivity": "Conectividade",
        "settings_test_providers": "Testar fornecedores",
        "settings_testing": "Testando…",
        "settings_aircraft_returned": "aeronaves retornadas",
        # Timezone and language
        "settings_language": "Idioma",
        "settings_timezone": "Fuso horário",
        "timezone_label": "Fuso horário do painel",
        # Status messages
        "status_healthy": "Saudável",
        "status_not_ready": "Não pronto",
        "status_no_poll": "Nenhuma consulta",
        "status_last_sync": "Última sincronização",
        "status_no_sync": "Nenhuma sincronização",
    },
    "en": {
        # Event types
        "event_probable_stop": "Possible Landing",
        "event_disappearance": "Disappearance",
        # Aircraft classifications
        "class_scheduled_airline": "Scheduled airline",
        "class_unknown_candidate": "Unknown candidate",
        "class_non_airline_candidate": "Non-airline candidate",
        # Phase names
        "phase_shadow": "Shadow",
        "phase_review": "Review",
        "phase_live": "Live",
        # Review statuses
        "review_unreviewed": "Unreviewed",
        "review_useful": "Useful",
        "review_noise": "Noise",
        "review_uncertain": "Uncertain",
        # Area categories
        "category_indigenous_territory": "Indigenous territory",
        "category_conservation_unit": "Conservation unit",
        # Email
        "email_title": "Flight Geofence Alerts",
        "email_event": "Event",
        "email_aircraft": "Aircraft",
        "email_callsign": "Callsign",
        "email_registration": "Registration",
        "email_aircraft_type": "Aircraft type",
        "email_protected_areas": "Protected areas",
        "email_time": "Time",
        "email_last_position": "Last position",
        "email_altitude": "Altitude",
        "email_ground_speed": "Ground speed",
        "email_provider": "Provider",
        "email_source_type": "Source type",
        "email_origin": "Origin",
        "email_destination": "Destination",
        "email_reason": "Reason",
        "email_classification": "Classification",
        "email_disclaimer": "This is an unverified monitoring signal. It does not prove landing, intentional transponder shutdown, illegal mining, or wrongdoing. Verify it with other evidence before acting.",
        "email_possible_stop": "Possible landing",
        "email_disappeared": "Aircraft position disappeared",
        "email_unavailable": "Unavailable",
        "email_footer": "Flight Geofence Alerts — Territorial monitoring",
        # Dashboard
        "nav_dashboard": "Dashboard",
        "nav_areas": "Protected areas",
        "nav_events": "Review events",
        "nav_settings": "Settings",
        "login_title": "Protected monitoring interface",
        "login_subtitle": "Use the password configured as",
        "login_button": "Log in",
        "login_password_label": "Password",
        "logout_button": "Log out",
        "phase_badge": "Phase",
        "dashboard_subtitle": "Territorial monitoring · real-data PoC",
        "dashboard_current_phase": "Current phase",
        "dashboard_three_phase": "Three-phase workflow",
        "shadow_description": "Real APIs and official boundaries. Events are stored, but no external alert is sent.",
        "review_description": "Classify events as useful, noise, or uncertain and adjust thresholds and selected areas.",
        "live_description": "Only probable landing and disappearance events trigger configured email delivery.",
        "dashboard_actions": "Actions",
        "dashboard_operations": "Operations",
        "sync_boundaries": "Sync official boundaries",
        "run_poll": "Run flight poll now",
        "test_email": "Test email delivery",
        "refresh_status": "Refresh status",
        "action_syncing": "Downloading and processing official boundaries…",
        "action_polling": "Polling flight providers…",
        "action_testing_email": "Testing email delivery…",
        "dashboard_recent": "Recent signals",
        "dashboard_events": "Suspicious events",
        "dashboard_no_events": "No suspicious events yet.",
        "metric_areas": "Protected areas",
        "metric_regions": "Query regions",
        "metric_events": "Events",
        "metric_last_poll": "Last poll",
        "metric_healthy": "Healthy",
        "metric_not_ready": "Not ready",
        "metric_no_poll": "No poll yet",
        "metric_reviewed": "reviewed useful",
        "metric_estimated": "estimated requests/day",
        "metric_downloaded": "downloaded",
        # Events table
        "col_time": "Time",
        "col_signal": "Signal",
        "col_aircraft": "Aircraft",
        "col_areas": "Areas",
        "col_telemetry": "Telemetry",
        "col_phase": "Phase",
        "col_review": "Review",
        "signal_stop": "Possible landing",
        "signal_disappeared": "Disappeared",
        # Areas
        "areas_subtitle": "Official FUNAI + CNUC data",
        "areas_title": "Select monitored areas",
        "areas_search": "Search name, state or phase",
        "areas_all_types": "All types",
        "areas_indigenous": "Indigenous territories",
        "areas_conservation": "Conservation units",
        "areas_all": "All",
        "areas_selected": "Selected",
        "areas_not_selected": "Not selected",
        "areas_filter": "Filter",
        "areas_select_visible": "Select visible",
        "areas_deselect_visible": "Deselect visible",
        "areas_select_filtered": "Select all filtered",
        "areas_matching": "matching areas",
        "col_monitor": "Monitor",
        "col_name": "Name",
        "col_type": "Type",
        "col_state": "State",
        "col_phase_category": "Phase/category",
        "col_source": "Source",
        "areas_no_data": "No areas found. Run boundary synchronization first.",
        # Events review
        "review_subtitle": "Calibration evidence",
        "review_title": "Review detected events",
        "review_all": "All reviews",
        "review_refresh": "Refresh",
        "review_save": "Save review",
        "review_no_events": "No matching events.",
        # Settings
        "settings_workflow": "Workflow",
        "settings_phase_providers": "Phase and providers",
        "settings_operating_phase": "Operating phase",
        "settings_flight_providers": "Flight providers",
        "settings_poll_interval": "Poll interval (seconds)",
        "settings_save_workflow": "Save workflow",
        "settings_saved": "Saved.",
        "settings_secrets": "Secrets",
        "settings_api_keys": "API keys",
        "settings_fr24_key": "Flightradar24 token",
        "settings_adsb_key": "ADS-B Exchange key",
        "settings_resend_key": "Resend API key",
        "settings_placeholder": "Leave blank to keep existing",
        "settings_save_keys": "Save keys securely",
        "settings_notifications": "Notifications",
        "settings_email": "Email",
        "settings_email_provider": "Email provider",
        "settings_console": "Console preview",
        "settings_recipients": "Recipients, comma-separated",
        "settings_sender": "Sender",
        "settings_smtp_host": "SMTP host",
        "settings_smtp_port": "SMTP port",
        "settings_smtp_user": "SMTP username",
        "settings_smtp_pass": "SMTP password",
        "settings_smtp_starttls": "Use STARTTLS",
        "settings_save_email": "Save email settings",
        "settings_detection": "Detection",
        "settings_noise": "Noise controls",
        "settings_stop_obs": "Landing observations",
        "settings_stop_duration": "Landing duration seconds",
        "settings_stationary_radius": "Stationary radius metres",
        "settings_max_stop_speed": "Maximum landing speed kt",
        "settings_disappear_obs": "Disappearance observations",
        "settings_disappear_polls": "Missing successful polls",
        "settings_disappear_alt": "Maximum disappearance altitude ft",
        "settings_outside_obs": "Outside observations to close episode",
        "settings_max_emails": "Daily email cap",
        "settings_save_thresholds": "Save thresholds",
        "settings_connectivity": "Connectivity",
        "settings_test_providers": "Test providers",
        "settings_testing": "Testing…",
        "settings_aircraft_returned": "aircraft returned",
        # Timezone and language
        "settings_language": "Language",
        "settings_timezone": "Timezone",
        "timezone_label": "Dashboard timezone",
        # Status messages
        "status_healthy": "Healthy",
        "status_not_ready": "Not ready",
        "status_no_poll": "No poll",
        "status_last_sync": "Last sync",
        "status_no_sync": "No sync",
    },
}


def t(key: str, lang: str = "en") -> str:
    """Translate a key to the specified language."""
    translations = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    return translations.get(key, TRANSLATIONS["en"].get(key, key))


def translate_event_type(event_type: str, lang: str = "pt") -> str:
    """Translate event type code to human-readable text."""
    mapping = {
        "PROBABLE_STOP": "event_probable_stop",
        "DISAPPEARANCE": "event_disappearance",
    }
    key = mapping.get(event_type, event_type)
    return t(key, lang)


def translate_classification(classification: str, lang: str = "pt") -> str:
    """Translate aircraft classification to human-readable text."""
    mapping = {
        "scheduled_airline": "class_scheduled_airline",
        "unknown_candidate": "class_unknown_candidate",
        "non_airline_candidate": "class_non_airline_candidate",
    }
    key = mapping.get(classification, classification)
    return t(key, lang)


def translate_phase(phase: str, lang: str = "pt") -> str:
    """Translate phase name to human-readable text."""
    mapping = {
        "shadow": "phase_shadow",
        "review": "phase_review",
        "live": "phase_live",
    }
    key = mapping.get(phase, phase)
    return t(key, lang)


def translate_review_status(status: str, lang: str = "pt") -> str:
    """Translate review status to human-readable text."""
    mapping = {
        "unreviewed": "review_unreviewed",
        "useful": "review_useful",
        "noise": "review_noise",
        "uncertain": "review_uncertain",
    }
    key = mapping.get(status, status)
    return t(key, lang)


def translate_category(category: str, lang: str = "pt") -> str:
    """Translate area category to human-readable text."""
    mapping = {
        "indigenous_territory": "category_indigenous_territory",
        "conservation_unit": "category_conservation_unit",
    }
    key = mapping.get(category, category)
    return t(key, lang)


def get_aircraft_type_url(aircraft_type: str | None) -> str | None:
    """Get a URL for aircraft type information."""
    if not aircraft_type:
        return None
    return f"https://www.flightradar24.com/data/aircraft/{aircraft_type.lower()}"



