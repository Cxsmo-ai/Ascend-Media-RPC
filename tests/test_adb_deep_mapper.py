import json

from tools.adb_deep_mapper import DeepMapper, parse_bounds, parse_package_names, parse_service_names, parse_ui_xml, safe_name


SAMPLE_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="app.wako" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[0,0][1920,1080]">
    <node index="1" text="Play" resource-id="app.wako:id/play" class="android.widget.Button" package="app.wako" content-desc="Play episode" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="true" scrollable="false" long-clickable="true" password="false" selected="false" bounds="[100,200][300,300]" />
  </node>
</hierarchy>"""


def test_parse_ui_xml_maps_text_flags_centers_and_commands():
    nodes = parse_ui_xml(SAMPLE_XML)
    assert len(nodes) == 2
    button = nodes[1]
    assert button["parent_index"] == 0
    assert button["text"] == "Play"
    assert button["content_desc"] == "Play episode"
    assert button["clickable"] is True
    assert button["focused"] is True
    assert (button["center_x"], button["center_y"]) == (200, 250)
    assert button["tap_command"] == "input tap 200 250"
    assert button["long_press_command"].endswith("200 250 800")


def test_bounds_rejects_invalid_geometry():
    assert parse_bounds("[1,2][3,4]") == (1, 2, 3, 4)
    assert parse_bounds("[3,4][1,2]") is None
    assert parse_bounds("bad") is None


def test_dynamic_name_parsers_reject_shell_metacharacters():
    assert parse_service_names("activity\nmedia_session\nbad;rm -rf /\n") == ["activity", "media_session"]
    packages = parse_package_names("package:/data/app/base.apk=app.wako installer=com.android.vending uid:10123\npackage:com.stremio.one\n")
    assert packages == ["app.wako", "com.stremio.one"]
    assert safe_name("../../bad:name") == "bad_name"


def test_run_wide_catalog_merges_changed_screens(tmp_path):
    mapper = DeepMapper("192.0.2.1", 5555, tmp_path)
    mapper.run_dir = tmp_path / "run"
    screen_dir = mapper.run_dir / "screens" / "initial"
    screen_dir.mkdir(parents=True)
    nodes = parse_ui_xml(SAMPLE_XML)
    (screen_dir / "nodes.json").write_text(json.dumps(nodes), encoding="utf-8")
    mapper.manifest = {"probes": [], "screens": [{
        "label": "initial", "captured_at": "2026-01-01T00:00:00Z", "path": "screens/initial"
    }]}

    mapper._write_global_ui_catalogs()

    assert (mapper.run_dir / "catalogs" / "all_ui_nodes.csv").exists()
    assert (mapper.run_dir / "catalogs" / "all_click_targets.csv").exists()
    assert "Play" in (mapper.run_dir / "catalogs" / "all_visible_text.txt").read_text(encoding="utf-8")
    assert mapper.manifest["ui_catalog"]["node_occurrences"] == 2
    assert mapper.manifest["ui_catalog"]["click_target_occurrences"] == 1


def test_stop_request_prevents_additional_curated_probes(tmp_path):
    mapper = DeepMapper("192.0.2.1", 5555, tmp_path)
    mapper._user_stop.set()
    calls = []
    mapper.save_probe = lambda probe: calls.append(probe)
    mapper.run_curated()
    assert calls == []
