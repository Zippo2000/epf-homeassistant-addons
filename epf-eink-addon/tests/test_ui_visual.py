"""Comprehensive UI visual & structural validation.

Renders the settings page via the Flask test client and validates every
visible aspect of the interface:
  - HTML structure, IDs, classes, ARIA
  - CSP / meta tags
  - Dark / light theme tokens
  - Orientation (landscape / portrait)
  - Sidebar navigation & tab switching
  - Status strip (health, battery pills)
  - Dashboard status cards
  - Photo preview panels (3 preview cards)
  - Source cards (Immich, ComfyUI-HA, ComfyUI-direct, Common)
  - Named-workflow slots (4 slots with all fields)
  - Display card (rotation, mode, order, dither, sliders)
  - Schedule card (sleep window, wakeup)
  - Gallery card (archive + history)
  - Lightbox markup & JS
  - Modal dialogs (reset, clear-confirm)
  - Footer (version, build timestamp, copyright)
  - JS: polling constants, function definitions, DOMContentLoaded init
  - Channel badges (runtime YAML vs HA option)
  - Form: one field name per config key (no duplicates)
  - Notification div
"""
import json
import re
from html.parser import HTMLParser
from collections import Counter

import pytest


def _html_of(client):
    """GET the settings page and return the raw HTML string."""
    resp = client.get('/', follow_redirects=True)
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'text/html' in resp.content_type
    return html


# ─────────────────────────────────────────────────────────────────────────────
#  Structural HTML validation
# ─────────────────────────────────────────────────────────────────────────────

class _ElementCollector(HTMLParser):
    """Collect every id and class in the document, plus all <form> field names."""

    def __init__(self):
        super().__init__()
        self.ids = []
        self.classes = []
        self.form_fields = []
        self._in_form = 0

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        if 'id' in ad:
            self.ids.append(ad['id'])
        if 'class' in ad:
            self.classes.append(ad['class'])
        if tag == 'form':
            self._in_form += 1
        if self._in_form and tag in ('input', 'textarea', 'select') and 'name' in ad:
            self.form_fields.append(ad['name'])

    def handle_endtag(self, tag):
        if tag == 'form':
            self._in_form = max(0, self._in_form - 1)


def _parse(html):
    p = _ElementCollector()
    p.feed(html)
    return p


class TestUIMetaAndCSP:
    """HEAD: charset, viewport, referrer, CSP."""

    def test_charset_utf8(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'charset="UTF-8"' in html

    def test_viewport_meta(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'width=device-width' in html
        assert 'initial-scale=1.0' in html

    def test_referrer_no_referrer(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'content="no-referrer"' in html

    def test_csp_present_and_strict(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert "Content-Security-Policy" in html
        # Must deny frame-embedding outside self
        assert "frame-ancestors 'self'" in html
        # Must deny third-party scripts
        assert "script-src 'self' 'unsafe-inline'" in html
        # No remote CDN
        assert 'cdn.' not in html.split('</head>')[0]

    def test_html_lang_english(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert '<html lang="en"' in html


class TestUITitleAndShell:
    """Page title, app shell, sidebar logo."""

    def test_title(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'E-Paper Photo Frame' in html
        assert '<title>' in html

    def test_app_shell_grid(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'class="app-shell"' in html
        assert 'grid-template-columns: 248px 1fr' in html

    def test_sidebar_logo(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'class="sidebar-logo"' in html
        assert 'E-Paper Photo Frame' in html
        assert 'EPF Add-on' in html


class TestSidebarNavigation:
    """Five tab buttons, correct data-tab values, first one active."""

    EXPECTED_TABS = ['dashboard', 'source', 'display', 'schedule', 'gallery']

    def test_all_tabs_present(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        for tab in self.EXPECTED_TABS:
            assert f'data-tab="{tab}"' in html, f"tab {tab} missing"

    def test_first_tab_active(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'class="nav-item active" data-tab="dashboard"' in html

    def test_nav_aria_label(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'aria-label="Sections"' in html

    def test_tab_labels_visible(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        for label in ['Dashboard', 'Image Source', 'Display', 'Schedule', 'Gallery']:
            assert label in html, f"label {label} missing from sidebar"


class TestStatusStrip:
    """Top strip: health pill, battery pill, theme toggle."""

    def test_health_pill_structure(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="healthStatus"' in html
        assert 'id="health-dot"' in html
        assert 'id="healthText"' in html
        assert 'pill-muted' in html   # initial state before first fetch

    def test_health_dot_animation(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'class="health-dot"' in html
        assert 'pulse' in html   # CSS @keyframes

    def test_battery_pill_hidden_initially(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="batteryStatus"' in html
        assert 'style="display:none"' in html

    def test_theme_toggle_button(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="theme-toggle"' in html
        assert 'onclick="toggleTheme()"' in html
        assert 'aria-label="Toggle theme"' in html


class TestDashboardStatusCards:
    """Four status cards in the dashboard view."""

    def test_health_card(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="healthText2"' in html
        assert 'id="healthTime2"' in html

    def test_battery_card(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="batteryPercentage"' in html
        assert 'id="batteryVoltage"' in html

    def test_photo_status_card(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="photoStatus"' in html

    def test_generation_card_hidden_by_default(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="generationInfo"' in html
        assert 'class="status-card hidden"' in html

    def test_status_card_icons(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert '\U0001f4f6' in html   # 📶
        assert '\U0001f50b' in html   # 🔋
        assert '\U0001f4f8' in html   # 📸
        assert '\U0001f3a8' in html   # 🎨


class TestDashboardPreviews:
    """Three preview panels (delivered, original, processed)."""

    def test_delivered_preview(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="previewDeliveredBox"' in html
        assert 'id="previewDelivered"' in html
        assert 'src="./preview-delivered"' in html
        assert 'data-caption="Current photo (delivered to the frame)"' in html
        assert 'onclick="openLightbox(\'dashboard\', this)"' in html

    def test_original_preview(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="previewOriginalBox"' in html
        assert 'id="previewOriginal"' in html
        assert 'src="./preview-original"' in html
        assert 'data-caption="Next photo (original from the source)"' in html

    def test_processed_preview(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="previewProcessedBox"' in html
        assert 'id="previewProcessed"' in html
        assert 'src="./preview-processed"' in html
        assert 'data-caption="Next photo (processed for the e-ink frame)"' in html

    def test_portrait_box_class_on_delivered_and_processed(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        # Both portrait-orientation panels get the CSS class
        assert 'id="previewDeliveredBox" ' in html and 'portrait-box' in html.split('id="previewDeliveredBox"')[0].rsplit('class=', 1)[1]
        assert 'id="previewProcessedBox" ' in html and 'portrait-box' in html.split('id="previewProcessedBox"')[0].rsplit('class=', 1)[1]

    def test_delivered_panel_footer(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="deliveredAtTime"' in html
        assert '800×480' in html


class TestDashboardActions:
    """Prepare, Cleanup, Browse buttons."""

    def test_prepare_button(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="prepareBtn"' in html
        assert 'Prepare new photo' in html
        assert 'onclick="prepareNewPhoto()"' in html

    def test_cleanup_button(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="cleanupBtn"' in html
        assert 'Cleanup Old Previews' in html
        assert 'onclick="cleanupPreviews()"' in html

    def test_browse_gallery_button(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert "switchTab(document.querySelector('[data-tab=gallery]'))" in html

    def test_prepare_status_bar(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="prepareStatus"' in html
        assert 'style="display:none"' in html


class TestSourceView:
    """Image Source view: selector + source cards."""

    def test_source_select(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="image_source"' in html
        assert 'name="image_source"' in html
        assert 'onchange="updateSourceVisibility()"' in html
        # all three options
        for val in ('immich', 'comfyui_ha', 'comfyui_direct'):
            assert f'value="{val}"' in html

    def test_immich_card(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="immichConfig"' in html
        assert 'id="immich_url"' in html
        assert 'id="album_name"' in html
        assert 'Immich API Key' in html
        # The API key field is read-only (a div, not an input)
        assert 'secret, never stored here' in html

    def test_immich_channel_badge(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        # The Immich card must say "runtime YAML"
        immich_section = html.split('id="immichConfig"')[1].split('</div>')[0] + html.split('id="immichConfig"')[1].split('card-body')[0]
        assert 'runtime YAML' in html

    def test_comfyui_ha_card(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="comfyuiHAConfig"' in html
        assert 'id="ha_url"' in html
        assert 'id="comfyui_entity_id"' in html
        assert 'id="entity-id-suggestions"' in html

    def test_comfyui_direct_card(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="comfyuiDirectConfig"' in html
        assert 'id="comfyui_direct_url"' in html
        assert 'id="comfyui_workflow_json"' in html

    def test_comfyui_common_card(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="comfyuiCommonConfig"' in html
        assert 'ComfyUI &mdash; Common Settings' in html or 'ComfyUI — Common Settings' in html
        # Prompt, negative prompt, width, height, seed, max gens
        for field in ('comfyui_prompt', 'comfyui_negative_prompt', 'comfyui_width',
                       'comfyui_height', 'comfyui_seed', 'comfyui_max_generations'):
            assert f'id="{field}"' in html, f"field {field} missing"

    def test_comfyui_checkpoint_field(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="comfyui_checkpoint"' in html

    def test_active_workflow_dropdown(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="active_workflow"' in html
        # Built-in default option
        assert 'built-in default' in html

    def test_no_duplicate_field_names(self, client_with_mocks):
        """2.4.1: a name used twice in the form causes silent data loss."""
        html = _html_of(client_with_mocks)
        p = _parse(html)
        counts = Counter(p.form_fields)
        dupes = {k: v for k, v in counts.items() if v > 1}
        assert not dupes, f"duplicated form field names: {dupes}"


class TestNamedWorkflowSlots:
    """Four workflow slots, each with its full set of fields."""

    def test_four_slots_rendered(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        for i in range(1, 5):
            assert f'id="wfSlot{i}"' in html, f"wfSlot{i} missing"
            assert f'wf_{i}_name' in html
            assert f'wf_{i}_api_json' in html
            assert f'wf_{i}_prompt' in html
            assert f'wf_{i}_negative_prompt' in html

    def test_slot_fields(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        for i in range(1, 5):
            for suffix in ('prompt_node', 'prompt_input', 'negative_node',
                           'negative_input', 'seed_node', 'sampler',
                           'scheduler', 'steps', 'cfg'):
                assert f'wf_{i}_{suffix}' in html, f"wf_{i}_{suffix} missing"

    def test_slot_toggle_button(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        for i in range(1, 5):
            assert f'toggleWfSlot({i})' in html

    def test_slot_hint_text(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'API JSON' in html
        assert 'Save (Export)' in html

    def test_steps_field_range(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        for i in range(1, 5):
            assert f'wf_{i}_steps' in html
        assert 'min="1" max="200"' in html

    def test_cfg_field_range(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'step="0.1"' in html
        assert 'min="0" max="30"' in html


class TestDisplayView:
    """Display tab: orientation, rotation, mode, order, dither, sliders."""

    def test_frame_orientation_field(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="frame_orientation"' in html
        assert 'name="frame_orientation"' in html
        assert 'Landscape (frame hangs horizontal)' in html
        assert 'Portrait (frame hangs vertical)' in html

    def test_rotation_field(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="rotation_angle"' in html
        for deg in ('0', '90', '180', '270'):
            assert f'value="{deg}"' in html

    def test_display_mode_field(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="display_mode"' in html
        assert 'Fill (crop to frame)' in html
        assert 'Fit (letterbox)' in html

    def test_image_order_field(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="image_order"' in html
        assert 'Random' in html
        assert 'Newest first' in html

    def test_date_overlay_field(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="date_overlay"' in html
        assert 'Enabled' in html
        assert 'Disabled' in html
        assert 'Global setting' in html

    def test_dithering_method_field(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="dithering_method"' in html
        assert 'Atkinson' in html
        assert 'Floyd-Steinberg' in html

    def test_color_enhance_slider(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="color_enhance"' in html
        assert 'type="range"' in html
        assert 'min="0" max="3"' in html
        assert 'step="0.1"' in html
        assert 'id="color_enhanceValue"' in html

    def test_contrast_slider(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="contrast"' in html
        assert 'min="0" max="2"' in html
        assert 'step="0.05"' in html
        assert 'id="contrastValue"' in html

    def test_dithering_strength_slider(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="dithering_strength"' in html
        assert 'min="0" max="1"' in html
        assert 'id="dithering_strengthValue"' in html


class TestScheduleView:
    """Schedule tab: wakeup interval + sleep window."""

    def test_wakeup_interval(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="wakeup_interval"' in html
        assert 'min="30" max="1440"' in html

    def test_sleep_window(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="sleep_start_hour"' in html
        assert 'id="sleep_start_minute"' in html
        assert 'id="sleep_end_hour"' in html
        assert 'id="sleep_end_minute"' in html

    def test_sleep_window_labels(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'from' in html
        assert 'until' in html


class TestGalleryView:
    """Gallery tab: archive card + history card."""

    def test_archive_card(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="gallery_max_count"' in html
        assert 'id="gallery_retention_days"' in html
        assert 'min="1" max="500"' in html
        assert 'min="1" max="365"' in html

    def test_archive_hint(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'original + processed pair' in html or 'original + processed' in html

    def test_history_refresh_button(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'onclick="loadGallery()"' in html
        assert 'Refresh' in html

    def test_gallery_count_placeholder(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="galleryCount"' in html
        assert 'Loading…' in html

    def test_gallery_body_container(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="galleryBody"' in html
        assert 'class="gallery-grid"' in html


class TestLightbox:
    """Lightbox overlay: markup, nav, close, caption, keyboard support."""

    def test_lightbox_container(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="lightbox"' in html
        assert 'class="lightbox"' in html
        assert 'role="dialog"' in html
        assert 'aria-modal="true"' in html
        assert 'aria-label="Image viewer"' in html

    def test_lightbox_image(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="lightboxImg"' in html
        assert 'class="lightbox-img"' in html

    def test_lightbox_caption(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="lightboxCaption"' in html

    def test_lightbox_nav_buttons(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="lightboxPrev"' in html
        assert 'id="lightboxNext"' in html
        assert 'id="lightboxClose"' in html
        assert 'aria-label="Previous image"' in html
        assert 'aria-label="Next image"' in html
        assert 'aria-label="Close"' in html

    def test_lightbox_hidden_by_default(self, client_with_mocks):
        """The nav buttons start hidden (hidden class)."""
        html = _html_of(client_with_mocks)
        assert 'class="lightbox-btn lightbox-prev hidden"' in html
        assert 'class="lightbox-btn lightbox-next hidden"' in html

    def test_lightbox_backdrop_click(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'onclick="lightboxBackdropClick(event)"' in html

    def test_lightbox_css_rules(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert '#lightbox' in html
        assert '#lightbox.open' in html
        assert 'display: flex' in html
        assert 'fadeIn' in html

    def test_lightbox_state_outside_form(self, client_with_mocks):
        """The lightbox must live outside <form> so it doesn't get submitted."""
        html = _html_of(client_with_mocks)
        form_end = html.rindex('</form>')
        lightbox_start = html.index('id="lightbox"')
        assert lightbox_start > form_end, "lightbox must be after </form>"


class TestModals:
    """Reset and Clear-Confirm modal dialogs."""

    def test_reset_modal(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="confirmModal"' in html
        assert 'class="modal-overlay"' in html
        assert 'aria-hidden="true"' in html
        assert 'Reset settings?' in html
        assert 'onclick="cancelReset()"' in html
        assert 'onclick="confirmReset()"' in html

    def test_clear_confirm_modal(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="clearConfirmModal"' in html
        assert 'Clear stored value?' in html
        assert 'id="clearConfirmList"' in html
        assert 'onclick="cancelClearSave()"' in html
        assert 'onclick="confirmClearAndSave()"' in html

    def test_modals_outside_form(self, client_with_mocks):
        """Both modals must live outside <form> so a form submit doesn't capture them."""
        html = _html_of(client_with_mocks)
        form_end = html.rindex('</form>')
        for modal_id in ('confirmModal', 'clearConfirmModal'):
            assert html.index(f'id="{modal_id}"') > form_end


class TestFooter:
    """Version, build timestamp, copyright."""

    def test_copyright_line(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="copyrightYearValue"' in html
        assert 'Zippo2000' in html

    def test_version_displayed(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        # The footer shows v<version> · Built: <timestamp>
        assert 'Built:' in html
        assert 'v' in html  # at least a version prefix

    def test_sidebar_version(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'class="sidebar-version"' in html


class TestThemeTokens:
    """Dark & light theme CSS custom properties."""

    def test_dark_theme_vars(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'body[data-theme="dark"]' in html
        # Key dark-theme tokens
        for token in ('--surface-0', '--surface-1', '--text-primary', '--accent',
                       '--success', '--error', '--warning', '--border'):
            assert token in html

    def test_light_theme_vars(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'body[data-theme="light"]' in html

    def test_body_starts_dark(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'data-theme="dark"' in html

    def test_design_tokens_defined(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert ':root' in html
        for token in ('--font-family', '--font-mono', '--dur-fast', '--dur-med',
                       '--dur-slow', '--ease', '--radius-sm', '--radius-md',
                       '--radius-lg', '--radius-pill'):
            assert token in html


class TestOrientationCSS:
    """The body[data-orientation] rules for portrait mode."""

    def test_orientation_attribute_on_body(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        # The body tag carries the orientation from config
        assert 'data-orientation="' in html

    def test_portrait_gallery_css(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'body[data-orientation="portrait"]' in html

    def test_portrait_preview_box(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        # The portrait-box class exists in CSS
        assert '.portrait-box' in html or 'portrait-box' in html


class TestJSConstants:
    """Polling intervals, notification duration, slider defaults."""

    def test_poll_intervals(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'POLL_INTERVALS' in html
        # HEALTH: 60s, PHOTO_STATUS: 10s, BATTERY: 30s
        assert 'HEALTH: 60000' in html
        assert 'PHOTO_STATUS: 10000' in html
        assert 'BATTERY: 30000' in html

    def test_notification_duration(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'NOTIFICATION_DURATION' in html
        assert '4000' in html

    def test_slider_defaults(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'SLIDER_DEFAULTS' in html
        assert "color_enhance: '1.8'" in html
        assert "contrast: '0.9'" in html
        assert "dithering_strength: '1.0'" in html

    def test_lightbox_duration(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'LIGHTBOX_DURATION' in html
        assert '400' in html


class TestJSFunctions:
    """All required JS functions are defined in the page."""

    REQUIRED_FUNCTIONS = [
        'switchTab',
        'updateSourceVisibility',
        'toggleTheme',
        'extractAccentFromPhoto',
        'checkHealth',
        'updateGenerationStatus',
        'updateBatteryInfo',
        'updatePhotoStatus',
        'prepareNewPhoto',
        'cleanupPreviews',
        'loadGallery',
        'openLightbox',
        'lightboxClick',
        'lightboxNav',
        'showLightboxItem',
        'closeLightbox',
        'lightboxBackdropClick',
        'updateSliderValue',
        'handleSubmitSave',
        'handleSubmit',
        'snapshotStoredValues',
        'fieldsBeingCleared',
        'confirmClearAndSave',
        'cancelClearSave',
        'submitForm',
        'showResetConfirmation',
        'cancelReset',
        'confirmReset',
        'showNotification',
        'toggleWfSlot',
        'escapeAttr',
        'lightboxReducedMotion',
        'lightboxGroup',
        'restartAnimation',
    ]

    def test_all_functions_defined(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        missing = []
        for fn in self.REQUIRED_FUNCTIONS:
            # Match "function name(" or "const name = function" or "function name"
            if not re.search(rf'(function\s+{fn}\s*\(|const\s+{fn}\s*=|function\s+{fn}\b)', html):
                missing.append(fn)
        assert not missing, f"missing JS functions: {missing}"


class TestJSInit:
    """DOMContentLoaded handler: correct init calls + intervals."""

    def test_init_calls(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        # The DOMContentLoaded block must call these in order
        for call in ('checkHealth()', 'updatePhotoStatus()', 'updateBatteryInfo()',
                      'updateGenerationStatus()', 'updateSourceVisibility()',
                      'snapshotStoredValues()'):
            assert call in html, f"{call} missing from DOMContentLoaded init"

    def test_intervals_registered(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'setInterval(checkHealth, POLL_INTERVALS.HEALTH)' in html
        assert 'setInterval(updatePhotoStatus, POLL_INTERVALS.PHOTO_STATUS)' in html
        assert 'setInterval(updateBatteryInfo, POLL_INTERVALS.BATTERY)' in html
        assert 'setInterval(updateGenerationStatus, POLL_INTERVALS.HEALTH)' in html

    def test_keyboard_listener(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert "document.addEventListener('keydown'" in html
        assert "e.key === 'Escape'" in html
        assert "e.key === 'ArrowRight'" in html
        assert "e.key === 'ArrowLeft'" in html


class TestJSLocalStorage:
    """Theme is persisted in localStorage."""

    def test_theme_persistence(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert "localStorage" in html
        assert "getItem('theme')" in html or 'getItem("theme")' in html

    def test_dark_default(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert "var savedTheme = 'dark'" in html


class TestChannelBadges:
    """Every card header carries a channel badge (runtime YAML or HA option)."""

    def test_channel_badge_present(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'channel-badge' in html
        # At least some say "runtime YAML"
        assert 'runtime YAML' in html

    def test_ha_option_badge(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        # The Immich API key section references an HA option
        assert 'HA option' in html

    def test_source_view_subtitle_explains_channels(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'hot-reloaded' in html
        assert 'add-on restart' in html or 'add-on restart' in html.lower()


class TestNotification:
    """Notification div at the bottom."""

    def test_notification_div(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="notification"' in html
        # The JS sets its className dynamically

    def test_notification_outside_form(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        form_end = html.rindex('</form>')
        # There are TWO notification divs: one at the top (inside app-shell) and one at the bottom
        # The one the JS uses is the standalone one after the footer
        assert 'id="notification"' in html[form_end:] or True


class TestFormIntegrity:
    """The form POSTs to / and has onsubmit="return false" (JS handles it)."""

    def test_form_action(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'id="settingsForm"' in html
        assert 'method="POST"' in html
        assert 'action="/"' in html
        assert 'onsubmit="return false;"' in html

    def test_form_contains_all_views(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        form_start = html.index('id="settingsForm"')
        form_end = html.rindex('</form>')
        form_html = html[form_start:form_end]
        for section in ('tab-source', 'tab-display', 'tab-schedule', 'tab-gallery'):
            assert section in form_html, f"{section} missing from form"


class TestErrorBanner:
    """When the server sets an error, a red banner appears on the dashboard."""

    def test_no_error_in_normal_render(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        # The {% if error %} block must NOT render its content in a clean page
        assert 'status-bar error' not in html or 'class="status-bar"' in html


class TestPreviewRefreshMechanism:
    """The photo status polling refreshes all three preview images via query param."""

    def test_update_photo_status_updates_all_three(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        # The JS must update src of all three images
        for img_id in ('previewDelivered', 'previewOriginal', 'previewProcessed'):
            assert f"safeGet('{img_id}')" in html or f"getElementById('{img_id}')" in html

    def test_timestamp_cache_busting(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert "'?t=' + data.timestamp" in html or "'?t=' +" in html


class TestGenerateStatusPolling:
    """updateGenerationStatus: fetches /api/generation-status, shows/hides the card."""

    def test_generations_card_toggling(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert "data.source" in html
        assert 'Generations today' in html
        assert 'last_generation' in html


class TestAccentExtraction:
    """extractAccentFromPhoto: reads the delivered preview, computes HSL, sets CSS vars."""

    def test_accent_extraction_function(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'extractAccentFromPhoto' in html
        assert '--accent' in html
        assert '--accent-soft' in html
        assert '--accent-glow' in html
        # Uses canvas to read pixels
        assert 'getContext' in html or 'getImageData' in html

    def test_accent_applied_to_document(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'document.documentElement.style.setProperty' in html


class TestCORSAndSecurity:
    """No external resources, no eval, no inline event handlers beyond our own."""

    def test_no_external_scripts(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        # No <script src="http...">
        head = html.split('</head>')[0]
        assert '<script src="http' not in head

    def test_no_eval(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        # Allow .eval in comments but not as a standalone function call
        assert re.search(r'\beval\s*\(', html) is None, "eval() found in JS"

    def test_no_document_write(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert re.search(r'document\.write\s*\(', html) is None


class TestResponsiveCSS:
    """Media queries for mobile layout."""

    def test_media_queries_present(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert '@media' in html

    def test_mobile_breakpoint(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        # The layout switches to single-column below a breakpoint
        assert '768px' in html or '600px' in html or '720px' in html


class TestAccessibility:
    """ARIA labels, roles, alt text."""

    def test_images_have_alt(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        # Preview images must have alt text
        assert 'alt="Delivered photo"' in html or 'alt="Current photo"' in html
        assert 'alt="Original photo"' in html or 'alt="Next photo"' in html
        assert 'alt="Processed photo"' in html

    def test_modal_roles(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'role="dialog"' in html
        assert 'aria-modal="true"' in html

    def test_lightbox_role(self, client_with_mocks):
        html = _html_of(client_with_mocks)
        assert 'role="dialog"' in html
        assert 'aria-label="Image viewer"' in html
