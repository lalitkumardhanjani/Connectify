"""
Unit Tests: Core Utilities
(core/utils/string_utils.py, core/utils/url_utils.py)

Tests string parsing, template substitution, URL normalization,
and other utility functions used across pipelines.

Run with:
    pytest tests/unit/test_utils.py -v
"""

import pytest


# ===========================================================================
#  String Utils Tests
# ===========================================================================

class TestParsePreferredLocations:
    def test_comma_separated_locations(self):
        from core.utils.string_utils import parse_preferred_locations
        result = parse_preferred_locations("Bangalore, Remote, Hyderabad")
        assert result == ["Bangalore", "Remote", "Hyderabad"]

    def test_single_location(self):
        from core.utils.string_utils import parse_preferred_locations
        result = parse_preferred_locations("Delhi")
        assert result == ["Delhi"]

    def test_empty_string_returns_empty_list(self):
        from core.utils.string_utils import parse_preferred_locations
        result = parse_preferred_locations("")
        assert result == []

    def test_none_returns_empty_list(self):
        from core.utils.string_utils import parse_preferred_locations
        result = parse_preferred_locations(None)
        assert result == []

    def test_strips_whitespace(self):
        from core.utils.string_utils import parse_preferred_locations
        result = parse_preferred_locations("  Bangalore  ,  Remote  ")
        assert result == ["Bangalore", "Remote"]

    def test_ignores_blank_entries(self):
        from core.utils.string_utils import parse_preferred_locations
        result = parse_preferred_locations("Bangalore,,Remote,")
        assert "Bangalore" in result
        assert "Remote" in result
        assert "" not in result


# ===========================================================================
#  URL Utils Tests
# ===========================================================================

class TestIsValidExternalUrl:
    def test_http_url_is_valid(self):
        from core.utils.url_utils import is_valid_external_url
        assert is_valid_external_url("http://example.com/jobs/123") is True

    def test_https_url_is_valid(self):
        from core.utils.url_utils import is_valid_external_url
        assert is_valid_external_url("https://techcorp.com/careers/de") is True

    def test_empty_string_is_invalid(self):
        from core.utils.url_utils import is_valid_external_url
        assert is_valid_external_url("") is False

    def test_none_is_invalid(self):
        from core.utils.url_utils import is_valid_external_url
        assert is_valid_external_url(None) is False

    def test_linkedin_url_is_valid(self):
        from core.utils.url_utils import is_valid_external_url
        assert is_valid_external_url("https://www.linkedin.com/jobs/view/12345") is True


class TestNormalizeExternalUrl:
    def test_strips_query_string(self):
        from core.utils.url_utils import normalize_external_url
        result = normalize_external_url("https://example.com/jobs/1?ref=linkedin&utm=test")
        assert "?" not in result

    def test_strips_trailing_slash(self):
        from core.utils.url_utils import normalize_external_url
        result = normalize_external_url("https://example.com/jobs/1/")
        assert not result.endswith("/")

    def test_lowercases_url(self):
        from core.utils.url_utils import normalize_external_url
        result = normalize_external_url("HTTPS://EXAMPLE.COM/Jobs/1")
        assert result == result.lower()

    def test_empty_returns_empty(self):
        from core.utils.url_utils import normalize_external_url
        assert normalize_external_url("") == ""

    def test_none_returns_empty(self):
        from core.utils.url_utils import normalize_external_url
        assert normalize_external_url(None) == ""

    def test_same_url_with_different_query_deduplicates(self):
        from core.utils.url_utils import normalize_external_url
        a = normalize_external_url("https://company.com/j/1?ref=abc")
        b = normalize_external_url("https://company.com/j/1?ref=xyz")
        assert a == b, "Same base URL with different query should normalize to same string"


# ===========================================================================
#  Template Rendering / String Substitution
# ===========================================================================

class TestTemplateRendering:
    """
    Tests that pipeline message templates correctly substitute placeholder variables.
    These patterns appear in: email_template, message_template, referral_outreach template.
    """

    USER_VARS = {
        "{FIRST_NAME}": "Lalit",
        "{LAST_NAME}": "Kumar",
        "{EMAIL}": "lalit@test.com",
        "{PHONE_NUMBER}": "9999999999",
        "{EXPERIENCE}": "3.5 years",
        "{CURRENT_LOCATION}": "Jaipur",
        "{PREFERRED_LOCATIONS}": "Bangalore, Remote",
        "{CURRENT_CTC}": "15",
        "{EXPECTED_CTC}": "24",
        "{NOTICE_PERIOD}": "30 Days",
        "{LINKEDIN_PROFILE_URL}": "https://linkedin.com/in/lalit/",
        "{RESUME}": "https://short.ly/lalit",
        "{RECEIVER_NAME}": "Alice",
        "{COMPANY}": "TechCorp",
        "{JOB_URL}": "https://techcorp.com/j/1",
        "{POST_URL}": "https://linkedin.com/posts/123",
    }

    def _render(self, template: str) -> str:
        result = template
        for placeholder, value in self.USER_VARS.items():
            result = result.replace(placeholder, str(value))
        return result

    def test_email_template_substitution(self):
        template = "Hi,\n\nApplying for {POST_URL}.\n\nRegards,\n{FIRST_NAME} {LAST_NAME}\n{EMAIL}"
        result = self._render(template)
        assert "Lalit Kumar" in result
        assert "lalit@test.com" in result
        assert "{FIRST_NAME}" not in result
        assert "{POST_URL}" not in result

    def test_referral_template_substitution(self):
        template = "Hi {RECEIVER_NAME},\n\n{COMPANY} has an opening ({JOB_URL}).\n\nThanks,\n{FIRST_NAME}"
        result = self._render(template)
        assert "Alice" in result
        assert "TechCorp" in result
        assert "https://techcorp.com/j/1" in result
        assert "{RECEIVER_NAME}" not in result

    def test_linkedin_connect_note_substitution(self):
        template = "Hi {RECEIVER_NAME}, I'm a Data Engineer with {EXPERIENCE}. Resume: {RESUME}."
        result = self._render(template)
        assert "3.5 years" in result
        assert "https://short.ly/lalit" in result
        assert "{RESUME}" not in result

    def test_unreplaced_placeholder_survives(self):
        """Unknown placeholders should remain in the output (not crash)."""
        template = "Hello {UNKNOWN_FIELD}, greetings from {FIRST_NAME}."
        result = self._render(template)
        assert "{UNKNOWN_FIELD}" in result
        assert "Lalit" in result


# ===========================================================================
#  Engine Utility: flatten_dict / unflatten_dict
# ===========================================================================

class TestFlattenUnflatten:
    def test_flatten_simple_nested(self):
        from core.storage.engine import flatten_dict
        d = {"profile": {"first_name": "Alice", "last_name": "Smith"}}
        flat = flatten_dict(d)
        assert flat == {"profile.first_name": "Alice", "profile.last_name": "Smith"}

    def test_unflatten_simple(self):
        from core.storage.engine import unflatten_dict
        flat = {"profile.first_name": "Bob", "global_settings.database_type": "local"}
        nested = unflatten_dict(flat)
        assert nested["profile"]["first_name"] == "Bob"
        assert nested["global_settings"]["database_type"] == "local"

    def test_roundtrip_flatten_unflatten(self):
        from core.storage.engine import flatten_dict, unflatten_dict
        original = {
            "profile": {"name": "Test", "age": 30},
            "settings": {"debug": True, "level": 3},
        }
        assert unflatten_dict(flatten_dict(original)) == original

    def test_boolean_coercion_in_unflatten(self):
        from core.storage.engine import unflatten_dict
        flat = {"email_scraper.review_mode": "true", "email_scraper.filter_location_enabled": "false"}
        nested = unflatten_dict(flat)
        assert nested["email_scraper"]["review_mode"] is True
        assert nested["email_scraper"]["filter_location_enabled"] is False

    def test_list_coercion_in_unflatten(self):
        from core.storage.engine import unflatten_dict
        flat = {"email_scraper.search_keywords": '["Data Engineer", "ETL Engineer"]'}
        nested = unflatten_dict(flat)
        assert isinstance(nested["email_scraper"]["search_keywords"], list)
        assert "Data Engineer" in nested["email_scraper"]["search_keywords"]
