"""Unit tests for hapag_lloyd.output."""

import json
import os

from hapag_lloyd.output import build_output, make_output_path, save_json


class TestMakeOutputPathHappyPath:
    """make_output_path builds output/ORIGIN_to_DEST[_CONTAINER]_TIMESTAMP.json from cfg."""

    def test_basic_route_and_container_are_included_in_stem(self):
        cfg = {"start_location": "Nhava Sheva", "end_location": "Singapore", "container_type": "40HC"}
        path = make_output_path(cfg)

        assert path.startswith(os.path.join("output", "NHAVA_SHEVA_to_SINGAPORE_40HC_"))
        assert path.endswith(".json")

    def test_custom_folder_is_used_as_the_directory(self):
        cfg = {"start_location": "A", "end_location": "B", "container_type": "40HC"}
        path = make_output_path(cfg, folder="custom_out")

        assert path.startswith(os.path.join("custom_out", "A_to_B_40HC_"))

    def test_special_characters_in_location_names_are_slugified(self):
        cfg = {"start_location": "Ho Chi Minh (Cat Lai)", "end_location": "São Paulo", "container_type": "20DC"}
        path = make_output_path(cfg)

        stem = os.path.basename(path)
        assert stem.startswith("HO_CHI_MINH_CAT_LAI_to_S")
        assert " " not in stem
        assert "(" not in stem and ")" not in stem

    def test_timestamp_suffix_matches_expected_format(self):
        cfg = {"start_location": "A", "end_location": "B", "container_type": "40HC"}
        path = make_output_path(cfg)

        stem = os.path.splitext(os.path.basename(path))[0]
        timestamp = stem.split("_40HC_", 1)[1]
        # YYYY-MM-DD_HH-MM-SS
        assert len(timestamp) == 19
        assert timestamp[4] == "-" and timestamp[7] == "-" and timestamp[10] == "_"


class TestMakeOutputPathFailPath:
    """make_output_path degrades to placeholder names rather than raising on missing cfg keys."""

    def test_missing_start_and_end_location_fall_back_to_origin_dest_placeholders(self):
        path = make_output_path({})

        assert os.path.basename(path).startswith("ORIGIN_to_DEST_")

    def test_missing_container_type_omits_the_container_segment(self):
        cfg = {"start_location": "A", "end_location": "B"}
        path = make_output_path(cfg)

        stem = os.path.basename(path)
        assert stem.startswith("A_to_B_")
        # No extra "_<container>_" segment before the timestamp: exactly one
        # underscore-delimited token separates "B" from the timestamp digits.
        after_b = stem[len("A_to_B_"):]
        assert after_b[:4].isdigit()  # starts straight into the YYYY of the timestamp

    def test_empty_string_container_type_also_omits_the_segment(self):
        cfg = {"start_location": "A", "end_location": "B", "container_type": ""}
        path = make_output_path(cfg)

        assert os.path.basename(path).startswith("A_to_B_")


class TestSaveJsonHappyPath:
    """save_json writes pretty-printed UTF-8 JSON, creating parent directories as needed."""

    def test_creates_parent_directories_that_do_not_exist_yet(self, tmp_path):
        path = str(tmp_path / "nested" / "dir" / "out.json")
        save_json({"a": 1}, path)

        assert os.path.exists(path)

    def test_written_content_round_trips_through_json_load(self, tmp_path):
        path = str(tmp_path / "out.json")
        data = {"route": "A-B", "count": 3}
        save_json(data, path)

        with open(path, encoding="utf-8") as f:
            assert json.load(f) == data

    def test_non_ascii_characters_are_written_literally_not_escaped(self, tmp_path):
        path = str(tmp_path / "out.json")
        save_json({"port": "São Paulo"}, path)

        with open(path, encoding="utf-8") as f:
            raw = f.read()
        assert "São Paulo" in raw

    def test_existing_file_at_path_is_overwritten(self, tmp_path):
        path = str(tmp_path / "out.json")
        save_json({"a": 1}, path)
        save_json({"a": 2}, path)

        with open(path, encoding="utf-8") as f:
            assert json.load(f) == {"a": 2}


class TestSaveJsonFailPath:
    """save_json tolerates a bare filename (no directory component) without raising."""

    def test_path_with_no_directory_component_does_not_raise(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        save_json({"a": 1}, "bare_name.json")

        assert os.path.exists(tmp_path / "bare_name.json")


class TestBuildOutputHappyPath:
    """build_output assembles the four top-level sections of the saved payload."""

    def test_all_four_sections_are_present(self):
        cfg = {"start_location": "A", "end_location": "B"}
        result = build_output(cfg, {"quick_quote": {}}, [{"url": "x"}], {"offer_v4": {}})

        assert set(result.keys()) == {"config", "api_data", "visual_data", "api_responses"}
        assert result["visual_data"] == {"quick_quote": {}}
        assert result["api_responses"] == [{"url": "x"}]
        assert result["api_data"] == {"offer_v4": {}}

    def test_non_credential_config_fields_are_preserved(self):
        cfg = {"start_location": "A", "end_location": "B", "container_type": "40HC"}
        result = build_output(cfg, {}, [])

        assert result["config"] == cfg


class TestBuildOutputFailPath:
    """build_output strips credentials and tolerates a missing api_data rather than raising."""

    def test_email_and_password_are_stripped_from_saved_config(self):
        cfg = {"email": "user@example.com", "password": "secret", "start_location": "A"}
        result = build_output(cfg, {}, [])

        assert "email" not in result["config"]
        assert "password" not in result["config"]
        assert result["config"] == {"start_location": "A"}

    def test_missing_api_data_defaults_to_empty_dict(self):
        result = build_output({}, {}, [])

        assert result["api_data"] == {}

    def test_none_api_data_also_defaults_to_empty_dict(self):
        result = build_output({}, {}, [], api_data=None)

        assert result["api_data"] == {}
