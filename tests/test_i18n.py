"""Automated tests for i18n completeness and consistency."""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
I18N_PY = ROOT / "app" / "i18n.py"
INDEX_HTML = ROOT / "app" / "static" / "index.html"
APP_JS = ROOT / "app" / "static" / "app.js"
EMAILER_PY = ROOT / "app" / "emailer.py"


def _load_translations() -> dict[str, dict[str, str]]:
    """Load TRANSLATIONS dict from i18n.py by executing it."""
    tree = ast.parse(I18N_PY.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TRANSLATIONS":
                    ns: dict = {}
                    exec(compile(ast.Module(body=[node], type_ignores=[]), "<i18n>", "exec"), ns)
                    return ns["TRANSLATIONS"]
    raise AssertionError("TRANSLATIONS not found in i18n.py")


def _load_frontend_keys() -> set[str]:
    """Extract translation keys used in app.js t() calls."""
    content = APP_JS.read_text()
    # Match t("key") and t('key') but not things like code.textContent
    return set(re.findall(r'''(?<![.\w])t\(['"](\w+)['"]\)''', content))


def _load_html_i18n_keys() -> set[str]:
    """Extract data-i18n keys from index.html."""
    content = INDEX_HTML.read_text()
    return set(re.findall(r'data-i18n="(\w+)"', content))


class TestTranslationKeyParity:
    """EN and PT must have identical key sets."""

    def test_en_pt_same_keys(self):
        tr = _load_translations()
        assert "en" in tr and "pt" in tr
        en_keys = set(tr["en"].keys())
        pt_keys = set(tr["pt"].keys())
        missing_en = pt_keys - en_keys
        missing_pt = en_keys - pt_keys
        assert not missing_en, f"Keys in PT but missing from EN: {missing_en}"
        assert not missing_pt, f"Keys in EN but missing from PT: {missing_pt}"

    def test_no_key_maps_to_itself(self):
        """Every PT value should differ from its EN value (not just the key name)."""
        tr = _load_translations()
        same = {k for k in tr["en"] if tr["en"][k] == tr["pt"].get(k, "")}
        # Legitimately identical: product name, universal terms, city names
        legitimately_same = {"app_title", "email_altitude", "tz_manaus", "tz_belem",
                             "tz_riobranco", "tz_noronha", "err_boundaries_sync_running",
                             "nav_fr24", "fr24_subtitle"}
        same -= legitimately_same
        assert not same, f"Keys with identical EN/PT values (possibly untranslated): {same}"

    def test_fr24_budget_policy_keys_ship_in_both_languages(self):
        """The ten FR24 budget-policy panel keys must exist in EN and PT."""
        tr = _load_translations()
        expected = {
            "fr24_policy_title",
            "fr24_policy_label",
            "fr24_policy_current",
            "fr24_policy_choice_warn_only",
            "fr24_policy_choice_pause_fr24",
            "fr24_policy_choice_continue",
            "fr24_policy_effect_stop",
            "fr24_policy_effect_keep_polling",
            "fr24_policy_env_locked",
            "fr24_save_policy",
        }
        for lang in ("en", "pt"):
            missing = expected - set(tr[lang].keys())
            assert not missing, f"Missing FR24 budget-policy keys in {lang}: {missing}"


class TestHtmlI18nCoverage:
    """All visible HTML text should use data-i18n."""

    # Brand names and technical values that don't need translation
    EXCLUDED_TEXT = {
        "Flight Geofence Alerts",  # product name
        "ADMIN_PASSWORD",  # technical
        "UTC",  # universal
        "Resend",  # brand
        "SMTP",  # protocol
        "ADSB.lol",  # brand (inside data-i18n spans now)
        "Airplanes.live",  # brand
        "ADS-B Exchange",  # brand
        "Flightradar24",  # brand
        "Português",  # language name
        "English",  # language name
    }

    def test_all_html_data_i18n_keys_exist_in_translations(self):
        """Every data-i18n key in the HTML must exist in the translation dict."""
        tr = _load_translations()
        html_keys = _load_html_i18n_keys()
        en_keys = set(tr["en"].keys())
        missing = html_keys - en_keys
        assert not missing, f"HTML data-i18n keys missing from translations: {missing}"

    def test_title_has_i18n(self):
        """The <title> element should have a data-i18n attribute."""
        content = INDEX_HTML.read_text()
        assert 'data-i18n="app_title"' in content, "<title> missing data-i18n"


class TestFrontendKeyCoverage:
    """Frontend t() calls should use keys from the backend translations."""

    def test_all_frontend_keys_exist_in_translations(self):
        tr = _load_translations()
        frontend_keys = _load_frontend_keys()
        en_keys = set(tr["en"].keys())
        # Some keys are used as fallback patterns, not direct translations
        skip = {"key", "lang", "value", "error", "status"}
        missing = (frontend_keys - en_keys) - skip
        assert not missing, f"Frontend t() keys missing from translations: {missing}"


class TestNoHardcodedStrings:
    """Ensure no hardcoded user-visible strings remain in key locations."""

    def test_emailer_no_portuguese_day_names(self):
        """emailer.py should not contain hardcoded Portuguese day names."""
        content = EMAILER_PY.read_text()
        portuguese_days = ["Domingo", "Segunda-feira", "Terça-feira",
                           "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado"]
        found = [day for day in portuguese_days if day in content]
        assert not found, f"Hardcoded Portuguese day names found in emailer.py: {found}"

    def test_emailer_no_hardcoded_as_separator(self):
        """emailer.py should not contain hardcoded 'às' separator."""
        content = EMAILER_PY.read_text()
        # Check for the standalone word "às" in string literals (not in comments)
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"""['"]\s*às\s*['"]""", stripped):
                pytest.fail(f"Hardcoded 'às' separator found at emailer.py line {i}")

    def test_app_js_no_hardcoded_completed(self):
        """app.js should not contain hardcoded 'Completed.' string."""
        content = APP_JS.read_text()
        # Look for "Completed." as a standalone string (not inside t() call)
        assert '"Completed."' not in content, "Hardcoded 'Completed.' found in app.js"
        assert "'Completed.'" not in content, "Hardcoded 'Completed.' found in app.js"

    def test_app_js_no_hardcoded_controlled_by_env(self):
        """app.js should not contain hardcoded 'Controlled by environment variable'."""
        content = APP_JS.read_text()
        assert '"Controlled by environment variable"' not in content


class TestI18nEndpoint:
    """The /api/i18n endpoint should return valid translation data."""

    def test_i18n_function_returns_dict(self):
        """get_translations() should return a dict with 'en' and 'pt' keys."""
        from app.i18n import get_translations
        result = get_translations()
        assert isinstance(result, dict)
        assert "en" in result
        assert "pt" in result
        assert len(result["en"]) > 50, "EN translations seem incomplete"
        assert len(result["pt"]) > 50, "PT translations seem incomplete"

    def test_translate_weekday(self):
        """translate_weekday should return correct day names."""
        from app.i18n import translate_weekday
        assert translate_weekday(0, "en") == "Sunday"
        assert translate_weekday(0, "pt") == "Domingo"
        assert translate_weekday(1, "en") == "Monday"
        assert translate_weekday(1, "pt") == "Segunda-feira"
        assert translate_weekday(6, "en") == "Saturday"
        assert translate_weekday(6, "pt") == "Sábado"
