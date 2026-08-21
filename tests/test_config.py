"""Unit tests for hapag_lloyd.config.load_config (the DEFAULT_CONFIG <- config file
<- CLI flags merge). parse_args/argparse wiring itself is not tested here."""

import argparse
import json

from hapag_lloyd.config import DEFAULT_CONFIG, load_config


def _args(**overrides) -> argparse.Namespace:
    """Build a Namespace with the same defaults parse_args() would produce,
    so each test only needs to set the fields it cares about."""
    base = dict(
        config=None, headless=False, email="", password="",
        origin="", destination="", output="",
    )
    base.update(overrides)
    return argparse.Namespace(**base)


class TestLoadConfigDefaultsHappyPath:
    """With no config file and no CLI flags, load_config returns DEFAULT_CONFIG untouched."""

    def test_no_overrides_returns_the_defaults(self):
        cfg = load_config(_args())

        assert cfg["start_location"] == DEFAULT_CONFIG["start_location"]
        assert cfg["end_location"] == DEFAULT_CONFIG["end_location"]
        assert cfg["headless"] == DEFAULT_CONFIG["headless"]

    def test_returned_dict_is_a_copy_not_the_module_level_default(self):
        cfg = load_config(_args())
        cfg["start_location"] = "MUTATED"

        assert DEFAULT_CONFIG["start_location"] != "MUTATED"


class TestLoadConfigCliOverridesHappyPath:
    """Non-empty CLI flags override DEFAULT_CONFIG values."""

    def test_origin_flag_overrides_default_start_location(self):
        cfg = load_config(_args(origin="Rotterdam"))
        assert cfg["start_location"] == "Rotterdam"

    def test_destination_flag_overrides_default_end_location(self):
        cfg = load_config(_args(destination="Hamburg"))
        assert cfg["end_location"] == "Hamburg"

    def test_email_and_password_flags_override_defaults(self):
        cfg = load_config(_args(email="user@example.com", password="secret"))
        assert cfg["email"] == "user@example.com"
        assert cfg["password"] == "secret"

    def test_output_flag_overrides_default_output_file(self):
        cfg = load_config(_args(output="custom/out.json"))
        assert cfg["output_file"] == "custom/out.json"

    def test_headless_flag_true_forces_headless_true(self):
        cfg = load_config(_args(headless=True))
        assert cfg["headless"] is True


class TestLoadConfigCliOverridesFailPath:
    """Empty-string CLI flags are falsy and must NOT clobber existing defaults —
    load_config only applies an override dict entry when its value is truthy."""

    def test_empty_origin_flag_does_not_override_default_start_location(self):
        cfg = load_config(_args(origin=""))
        assert cfg["start_location"] == DEFAULT_CONFIG["start_location"]

    def test_empty_email_flag_does_not_override_default_email(self):
        cfg = load_config(_args(email=""))
        assert cfg["email"] == DEFAULT_CONFIG["email"]

    def test_headless_flag_false_does_not_force_headless_false(self):
        # args.headless=False is falsy, so "headless" is omitted from the applied
        # overrides and the existing cfg["headless"] value survives.
        cfg = load_config(_args(headless=False))
        assert cfg["headless"] == DEFAULT_CONFIG["headless"]


class TestLoadConfigFilePriorityHappyPath:
    """A config file overrides DEFAULT_CONFIG, and CLI flags in turn override
    the config file (CLI flags win the merge overall)."""

    def test_config_file_values_override_defaults(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"start_location": "Busan", "commodity": "REEFER"}), encoding="utf-8")

        cfg = load_config(_args(config=str(config_path)))

        assert cfg["start_location"] == "Busan"
        assert cfg["commodity"] == "REEFER"

    def test_config_file_values_not_touched_by_cli_are_kept(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"start_location": "Busan"}), encoding="utf-8")

        cfg = load_config(_args(config=str(config_path)))

        assert cfg["end_location"] == DEFAULT_CONFIG["end_location"]

    def test_cli_flag_wins_over_config_file_for_the_same_field(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"start_location": "Busan"}), encoding="utf-8")

        cfg = load_config(_args(config=str(config_path), origin="Rotterdam"))

        assert cfg["start_location"] == "Rotterdam"
