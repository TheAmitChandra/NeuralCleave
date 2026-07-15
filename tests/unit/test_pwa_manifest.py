"""Tests for cortexflow_ai.pwa.manifest.build_manifest()."""

from __future__ import annotations

import pytest

from cortexflow_ai.pwa.manifest import (
    APP_ICON_SVG,
    BACKGROUND_COLOR,
    THEME_COLOR,
    build_manifest,
)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_theme_color_is_hex(self):
        assert THEME_COLOR.startswith("#") and len(THEME_COLOR) == 7

    def test_background_color_is_hex(self):
        assert BACKGROUND_COLOR.startswith("#") and len(BACKGROUND_COLOR) == 7

    def test_app_icon_svg_is_valid_svg(self):
        assert "<svg" in APP_ICON_SVG
        assert "xmlns" in APP_ICON_SVG
        assert "</svg>" in APP_ICON_SVG

    def test_app_icon_svg_has_viewbox(self):
        assert "viewBox" in APP_ICON_SVG

    def test_app_icon_svg_non_empty(self):
        assert len(APP_ICON_SVG) > 100


# ---------------------------------------------------------------------------
# build_manifest return structure
# ---------------------------------------------------------------------------


class TestBuildManifest:
    @pytest.fixture
    def manifest(self):
        return build_manifest()

    def test_returns_dict(self, manifest):
        assert isinstance(manifest, dict)

    def test_name_field(self, manifest):
        assert manifest["name"] == "CortexFlow"

    def test_short_name_field(self, manifest):
        assert manifest["short_name"] == "CortexFlow"

    def test_description_non_empty(self, manifest):
        assert len(manifest["description"]) > 10

    def test_start_url(self, manifest):
        assert manifest["start_url"] == "/app"

    def test_scope_is_root(self, manifest):
        assert manifest["scope"] == "/"

    def test_display_standalone(self, manifest):
        assert manifest["display"] == "standalone"

    def test_orientation_portrait(self, manifest):
        assert "portrait" in manifest["orientation"]

    def test_theme_color_matches_constant(self, manifest):
        assert manifest["theme_color"] == THEME_COLOR

    def test_background_color_matches_constant(self, manifest):
        assert manifest["background_color"] == BACKGROUND_COLOR

    def test_lang_english(self, manifest):
        assert manifest["lang"] == "en"

    def test_dir_ltr(self, manifest):
        assert manifest["dir"] == "ltr"

    def test_categories_list(self, manifest):
        assert isinstance(manifest["categories"], list)
        assert len(manifest["categories"]) >= 1

    def test_prefer_related_applications_false(self, manifest):
        assert manifest["prefer_related_applications"] is False

    # ------------------------------------------------------------------
    # Icons
    # ------------------------------------------------------------------

    def test_icons_list_non_empty(self, manifest):
        assert isinstance(manifest["icons"], list)
        assert len(manifest["icons"]) >= 2

    def test_icons_have_required_fields(self, manifest):
        for icon in manifest["icons"]:
            assert "src" in icon
            assert "sizes" in icon
            assert "type" in icon

    def test_icon_192_present(self, manifest):
        sizes = [i["sizes"] for i in manifest["icons"]]
        assert "192x192" in sizes

    def test_icon_512_present(self, manifest):
        sizes = [i["sizes"] for i in manifest["icons"]]
        assert "512x512" in sizes

    def test_icons_are_svg(self, manifest):
        for icon in manifest["icons"]:
            assert icon["type"] == "image/svg+xml"

    def test_icons_have_purpose(self, manifest):
        for icon in manifest["icons"]:
            assert "purpose" in icon
            assert "any" in icon["purpose"] or "maskable" in icon["purpose"]

    def test_icon_src_starts_with_slash(self, manifest):
        for icon in manifest["icons"]:
            assert icon["src"].startswith("/")

    # ------------------------------------------------------------------
    # Shortcuts
    # ------------------------------------------------------------------

    def test_shortcuts_list(self, manifest):
        assert isinstance(manifest["shortcuts"], list)
        assert len(manifest["shortcuts"]) >= 1

    def test_shortcut_has_name(self, manifest):
        for s in manifest["shortcuts"]:
            assert "name" in s and s["name"]

    def test_shortcut_has_url(self, manifest):
        for s in manifest["shortcuts"]:
            assert "url" in s and s["url"].startswith("/")

    def test_shortcut_has_icons(self, manifest):
        for s in manifest["shortcuts"]:
            assert "icons" in s and len(s["icons"]) >= 1

    # ------------------------------------------------------------------
    # Serialisability
    # ------------------------------------------------------------------

    def test_manifest_is_json_serializable(self, manifest):
        import json

        dumped = json.dumps(manifest)
        reloaded = json.loads(dumped)
        assert reloaded["name"] == "CortexFlow"

    # ------------------------------------------------------------------
    # base_url parameter
    # ------------------------------------------------------------------

    def test_base_url_param_accepted(self):
        m = build_manifest(base_url="https://example.com")
        assert m["name"] == "CortexFlow"

    def test_base_url_default_empty_string(self):
        m1 = build_manifest()
        m2 = build_manifest(base_url="")
        assert m1 == m2

    # ------------------------------------------------------------------
    # Multiple calls return fresh dicts (no aliasing)
    # ------------------------------------------------------------------

    def test_multiple_calls_return_independent_dicts(self):
        m1 = build_manifest()
        m2 = build_manifest()
        m1["name"] = "Modified"
        assert m2["name"] == "CortexFlow"

    def test_icon_list_mutation_does_not_affect_next_call(self):
        m1 = build_manifest()
        m1["icons"].clear()
        m2 = build_manifest()
        assert len(m2["icons"]) >= 2

    # ------------------------------------------------------------------
    # W3C required fields present
    # ------------------------------------------------------------------

    def test_w3c_required_fields_present(self, manifest):
        required = {"name", "short_name", "start_url", "display", "icons"}
        assert required <= set(manifest.keys())

    def test_screenshots_field_is_list(self, manifest):
        assert isinstance(manifest["screenshots"], list)
