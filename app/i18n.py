"""Internationalization support for Flight Geofence Alerts.

Single source of truth for all EN/PT translation keys used by both the
Python backend and the JavaScript frontend (via ``/api/i18n``).
"""

TRANSLATIONS = {
    "pt": {
        # App title
        "app_title": "Flight Geofence Alerts",
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
        "phase_badge": "Fase",
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
        "email_open_event": "Abrir evento",
        "email_flight_number": "Número do voo",
        "email_tracking_services": "Serviços de rastreamento",
        "email_external_tracking_note": "Serviços de rastreamento externo podem não ter posição ou registro para todas as aeronaves.",
        "email_disclaimer": "Este é um sinal de monitoramento não verificado. Não prova pouso, desligamento intencional de transponder, mineração ilegal ou irregularidade. Verifique com outras evidências antes de agir.",
        "email_possible_stop": "Possível pouso",
        "email_disappeared": "Posição da aeronave desapareceu",
        "email_unavailable": "Indisponível",
        "email_footer": "Alertas de Geovoo de Voo — Monitoramento territorial",
        # Navigation
        "nav_dashboard": "Painel",
        "nav_areas": "Áreas protegidas",
        "nav_events": "Revisar eventos",
        "nav_settings": "Configurações",
        # Login
        "login_title": "Interface de monitoramento protegida",
        "login_subtitle": "Use a senha configurada como",
        "login_button": "Entrar",
        "login_password_label": "Senha",
        "logout_button": "Sair",
        # Dashboard
        "dashboard_subtitle": "Monitoramento territorial · PoC com dados reais",
        "dashboard_current_phase": "Fase atual",
        "dashboard_three_phase": "Fluxo de três fases",
        "shadow_desc": "APIs oficiais e limites oficiais. Eventos são armazenados, mas nenhum alerta externo é enviado.",
        "review_desc": "Classifique eventos como úteis, ruído ou incerto e ajuste limiares e áreas selecionadas.",
        "live_desc": "Apenas eventos de pouso provável e desaparecimento acionam a entrega de e-mail configurada.",
        "dashboard_actions": "Ações",
        "dashboard_operations": "Operações",
        "sync_boundaries": "Sincronizar limites oficiais",
        "run_poll": "Executar consulta de voo agora",
        "test_email": "Testar entrega de e-mail",
        "refresh_status": "Atualizar status",
        "action_syncing": "Baixando e processando limites oficiais…",
        "action_polling": "Consultando fornecedores de voo…",
        "action_testing_email": "Testando entrega de e-mail…",
        "action_completed": "Concluído.",
        "dashboard_recent": "Sinais recentes",
        "dashboard_events": "Eventos suspeitos",
        "no_events": "Nenhum evento suspeito ainda.",
        # Metrics
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
        "review_notes": "Notas",
        "test_button": "Testar",
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
        "settings_display": "Exibição",
        "settings_timezone": "Fuso horário",
        "timezone_label": "Fuso horário do painel",
        "settings_language": "Idioma",
        "time_at": " às ",
        # Timezone labels
        "tz_brasilia": "Horário de Brasília (UTC-3)",
        "tz_manaus": "Manaus (UTC-4)",
        "tz_belem": "Belém (UTC-3)",
        "tz_riobranco": "Rio Branco (UTC-5)",
        "tz_noronha": "Fernando de Noronha (UTC-2)",
        # Provider cost labels
        "provider_adsb_lol_cost": "ADSB.lol — dados abertos/gratuitos",
        "provider_airplanes_live_cost": "Airplanes.live — tier gratuito não-comercial",
        "provider_adsbexchange_cost": "ADS-B Exchange — pago",
        "provider_flightradar24_cost": "Flightradar24 — créditos pagos",
        # Environment / UI
        "env_controlled": "Controlado por variável de ambiente",
        # Status messages
        "status_healthy": "Saudável",
        "status_not_ready": "Não pronto",
        "status_no_poll": "Nenhuma consulta",
        "status_last_sync": "Última sincronização",
        "status_no_sync": "Nenhuma sincronização",
        # Dashboard warnings
        "warn_boundaries_not_synced": "Limites oficiais ainda não sincronizados.",
        "warn_no_areas_selected": "Nenhuma área protegida selecionada.",
        "warn_airplanes_limit": "Airplanes.live exigiria cerca de {n} requisições/dia; o app impõe o limite de 500.",
        "warn_flightradar_credits": "Flightradar24 cobra por voo retornado; regiões amplas sobrepostas podem consumir créditos rapidamente.",
        "warn_earliest_stop": "Com o intervalo atual, a confirmação de pouso provável mais cedo é de aproximadamente {n} minutos.",
        # Error messages
        "err_sync_running": "Sincronização de limites já em andamento",
        "err_poll_running": "Ciclo de cobertura já em andamento",
        "err_poll_running_process": "Ciclo de cobertura já em andamento em outro processo",
        "err_no_regions": "Nenhuma região de consulta. Sincronize e selecione áreas protegidas primeiro.",
        "err_invalid_csrf": "Token CSRF inválido",
        "err_db_failed": "Verificação do banco de dados falhou",
        "err_too_many_logins": "Muitas tentativas de login falharam",
        "err_invalid_password": "Senha inválida",
        "err_sync_conflict": "Sincronização de limites em andamento",
        "err_poll_conflict": "Consulta de voo em andamento",
        "err_invalid_review": "Status de revisão ou evento inválido",
        "err_email_test_failed": "Teste de e-mail falhou",
        "err_live_need_resend_smtp": "Escolha Resend ou SMTP antes de ativar a fase Ao vivo",
        "err_live_need_resend_key": "Chave da API Resend ausente",
        "err_live_need_smtp": "Host SMTP, nome de usuário e senha são obrigatórios",
        "err_live_need_recipients": "Pelo menos um destinatário de alerta é obrigatório",
        "err_config_test_area": "Teste de configuração",
        "err_config_test_reason": "Teste de configuração de e-mail; este não é um alerta de aeronave.",
        # Emailer errors
        "err_smtp_missing": "Host SMTP, nome de usuário ou senha ausente",
        "err_daily_cap": "Limite diário de e-mails atingido",
        "err_no_recipients": "Nenhum destinatário de alerta configurado",
        "err_invalid_sender": "EMAIL_FROM não é um endereço de remetente válido",
        "err_resend_key_missing": "Chave da API Resend ausente",
        "err_unsupported_email_provider": "Provedor de e-mail não suportado",
        # Provider errors
        "err_provider_daily_limit": "Limite diário de 500 requisições HTTP do Airplanes.live atingido",
        "err_provider_non_object": "O provedor retornou uma resposta JSON que não é um objeto",
        "err_provider_request_failed": "Solicitação ao provedor falhou",
        "err_adsbexchange_key_missing": "Chave da API ADS-B Exchange ausente",
        "err_unsupported_readsb_provider": "Provedor readsb não suportado",
        "err_flightradar24_key_missing": "Chave da API Flightradar24 ausente",
        "err_unknown_provider": "Provedor desconhecido",
        "err_select_areas_first": "Selecione áreas e gere regiões de cobertura primeiro",
        # Boundary sync errors
        "err_boundaries_sync_running": "Sincronização de limites já em andamento",
        "err_boundaries_poll_running": "Uma consulta de cobertura de voo está em andamento",
        "err_funai_download_failed": "Falha no download WFS da FUNAI; não é possível prosseguir sem dados de territórios indígenas",
        # Settings validation errors
        "err_value_bool": "O valor deve ser true ou false",
        "err_value_one_of": "O valor deve ser um de: {choices}",
        "err_unsupported_list_values": "Valores de lista não suportados: {values}",
        "err_value_min": "O valor deve ser pelo menos {min}",
        "err_value_max": "O valor deve ser no máximo {max}",
        "err_invalid_email": "Endereço(s) de e-mail inválido(s): {emails}",
        "err_controlled_by_env": "{key} é controlado pela variável de ambiente {env}",
        # Day names for emailer
        "day_sunday": "Domingo",
        "day_monday": "Segunda-feira",
        "day_tuesday": "Terça-feira",
        "day_wednesday": "Quarta-feira",
        "day_thursday": "Quinta-feira",
        "day_friday": "Sexta-feira",
        "day_saturday": "Sábado",
    },
    "en": {
        # App title
        "app_title": "Flight Geofence Alerts",
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
        "phase_badge": "Phase",
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
        "email_open_event": "Open event",
        "email_flight_number": "Flight number",
        "email_tracking_services": "Tracking services",
        "email_external_tracking_note": "External tracking services may not currently have a position or record for every aircraft.",
        "email_disclaimer": "This is an unverified monitoring signal. It does not prove landing, intentional transponder shutdown, illegal mining, or wrongdoing. Verify it with other evidence before acting.",
        "email_possible_stop": "Possible landing",
        "email_disappeared": "Aircraft position disappeared",
        "email_unavailable": "Unavailable",
        "email_footer": "Flight Geofence Alerts — Territorial monitoring",
        # Navigation
        "nav_dashboard": "Dashboard",
        "nav_areas": "Protected areas",
        "nav_events": "Review events",
        "nav_settings": "Settings",
        # Login
        "login_title": "Protected monitoring interface",
        "login_subtitle": "Use the password configured as",
        "login_button": "Log in",
        "login_password_label": "Password",
        "logout_button": "Log out",
        # Dashboard
        "dashboard_subtitle": "Territorial monitoring · real-data PoC",
        "dashboard_current_phase": "Current phase",
        "dashboard_three_phase": "Three-phase workflow",
        "shadow_desc": "Real APIs and official boundaries. Events are stored, but no external alert is sent.",
        "review_desc": "Classify events as useful, noise, or uncertain and adjust thresholds and selected areas.",
        "live_desc": "Only probable landing and disappearance events trigger configured email delivery.",
        "dashboard_actions": "Actions",
        "dashboard_operations": "Operations",
        "sync_boundaries": "Sync official boundaries",
        "run_poll": "Run flight poll now",
        "test_email": "Test email delivery",
        "refresh_status": "Refresh status",
        "action_syncing": "Downloading and processing official boundaries…",
        "action_polling": "Polling flight providers…",
        "action_testing_email": "Testing email delivery…",
        "action_completed": "Completed.",
        "dashboard_recent": "Recent signals",
        "dashboard_events": "Suspicious events",
        "no_events": "No suspicious events yet.",
        # Metrics
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
        "review_notes": "Notes",
        "test_button": "Test",
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
        "settings_stop_obs": "Stop observations",
        "settings_stop_duration": "Stop duration seconds",
        "settings_stationary_radius": "Stationary radius metres",
        "settings_max_stop_speed": "Maximum stop speed kt",
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
        "settings_display": "Display",
        "settings_timezone": "Timezone",
        "timezone_label": "Dashboard timezone",
        "settings_language": "Language",
        "time_at": " at ",
        # Timezone labels
        "tz_brasilia": "Brasília time (UTC-3)",
        "tz_manaus": "Manaus (UTC-4)",
        "tz_belem": "Belém (UTC-3)",
        "tz_riobranco": "Rio Branco (UTC-5)",
        "tz_noronha": "Fernando de Noronha (UTC-2)",
        # Provider cost labels
        "provider_adsb_lol_cost": "ADSB.lol — free/open",
        "provider_airplanes_live_cost": "Airplanes.live — free non-commercial",
        "provider_adsbexchange_cost": "ADS-B Exchange — paid",
        "provider_flightradar24_cost": "Flightradar24 — paid credits",
        # Environment / UI
        "env_controlled": "Controlled by environment variable",
        # Status messages
        "status_healthy": "Healthy",
        "status_not_ready": "Not ready",
        "status_no_poll": "No poll",
        "status_last_sync": "Last sync",
        "status_no_sync": "No sync",
        # Dashboard warnings
        "warn_boundaries_not_synced": "Official boundaries have not been synchronized yet.",
        "warn_no_areas_selected": "No protected areas are selected.",
        "warn_airplanes_limit": "Airplanes.live would require about {n} requests/day; the app enforces its 500-request daily ceiling.",
        "warn_flightradar_credits": "Flightradar24 charges per returned flight; overlapping broad regions can consume credits quickly.",
        "warn_earliest_stop": "With the current interval, the earliest probable-stop confirmation is roughly {n} minutes.",
        # Error messages
        "err_sync_running": "Boundary sync already running",
        "err_poll_running": "Coverage cycle already running",
        "err_poll_running_process": "Coverage cycle already running in another process",
        "err_no_regions": "No query regions. Sync and select protected areas first.",
        "err_invalid_csrf": "Invalid CSRF token",
        "err_db_failed": "Database check failed",
        "err_too_many_logins": "Too many failed login attempts",
        "err_invalid_password": "Invalid password",
        "err_sync_conflict": "Boundary sync is currently running",
        "err_poll_conflict": "Flight poll is currently running",
        "err_invalid_review": "Invalid review status or event",
        "err_email_test_failed": "Email test failed",
        "err_live_need_resend_smtp": "Choose Resend or SMTP before enabling Live phase",
        "err_live_need_resend_key": "Resend API key is missing",
        "err_live_need_smtp": "SMTP host, username and password are required",
        "err_live_need_recipients": "At least one alert recipient is required",
        "err_config_test_area": "Configuration test",
        "err_config_test_reason": "Email configuration test; this is not an aircraft alert.",
        # Emailer errors
        "err_smtp_missing": "SMTP host, username or password is missing",
        "err_daily_cap": "Daily email cap reached",
        "err_no_recipients": "No alert recipients configured",
        "err_invalid_sender": "EMAIL_FROM is not a valid sender address",
        "err_resend_key_missing": "Resend API key is missing",
        "err_unsupported_email_provider": "Unsupported email provider",
        # Provider errors
        "err_provider_daily_limit": "Airplanes.live daily limit of 500 HTTP requests reached",
        "err_provider_non_object": "Provider returned a non-object JSON response",
        "err_provider_request_failed": "Provider request failed",
        "err_adsbexchange_key_missing": "ADS-B Exchange API key is missing",
        "err_unsupported_readsb_provider": "Unsupported readsb provider",
        "err_flightradar24_key_missing": "Flightradar24 API key is missing",
        "err_unknown_provider": "Unknown provider",
        "err_select_areas_first": "Select areas and generate coverage regions first",
        # Boundary sync errors
        "err_boundaries_sync_running": "Boundary sync already running",
        "err_boundaries_poll_running": "A flight coverage poll is currently running",
        "err_funai_download_failed": "FUNAI WFS download failed; cannot proceed without indigenous territory data",
        # Settings validation errors
        "err_value_bool": "Value must be true or false",
        "err_value_one_of": "Value must be one of: {choices}",
        "err_unsupported_list_values": "Unsupported list values: {values}",
        "err_value_min": "Value must be at least {min}",
        "err_value_max": "Value must be at most {max}",
        "err_invalid_email": "Invalid email address(es): {emails}",
        "err_controlled_by_env": "{key} is controlled by environment variable {env}",
        # Day names for emailer
        "day_sunday": "Sunday",
        "day_monday": "Monday",
        "day_tuesday": "Tuesday",
        "day_wednesday": "Wednesday",
        "day_thursday": "Thursday",
        "day_friday": "Friday",
        "day_saturday": "Saturday",
    },
}

DAY_KEYS = [
    "day_sunday", "day_monday", "day_tuesday", "day_wednesday",
    "day_thursday", "day_friday", "day_saturday",
]


def t(key: str, lang: str = "en") -> str:
    """Translate a key to the specified language."""
    translations = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    return translations.get(key, TRANSLATIONS["en"].get(key, key))


def get_translations() -> dict[str, dict[str, str]]:
    """Return the full translation dictionaries for the frontend."""
    return TRANSLATIONS


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


def translate_weekday(index: int, lang: str = "pt") -> str:
    """Translate weekday index (0=Sunday) to localized name."""
    if 0 <= index < 7:
        return t(DAY_KEYS[index], lang)
    return str(index)
