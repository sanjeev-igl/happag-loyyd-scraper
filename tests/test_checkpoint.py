"""Unit tests for hapag_lloyd.checkpoint."""

import json

import pytest

from hapag_lloyd.checkpoint import (
    _key,
    is_done,
    load_checkpoint,
    mark_failed,
    mark_success,
)


class TestKeyHappyPath:
    """_key builds a case- and whitespace-normalized composite key so lookups
    are insensitive to how the route/container type was originally typed."""

    def test_key_is_uppercased(self):
        assert _key("nhava sheva", "singapore", "40hc") == "NHAVA SHEVA|SINGAPORE|40HC"

    def test_key_strips_surrounding_whitespace_on_each_part(self):
        assert _key("  Nhava Sheva  ", " Singapore ", " 40HC ") == "NHAVA SHEVA|SINGAPORE|40HC"

    def test_different_container_types_for_same_route_produce_different_keys(self):
        assert _key("A", "B", "20DC") != _key("A", "B", "40HC")

    def test_key_is_order_sensitive_between_origin_and_destination(self):
        assert _key("A", "B", "40HC") != _key("B", "A", "40HC")


class TestLoadCheckpointHappyPath:
    """load_checkpoint reads back the {key: entry} map written by mark_success/mark_failed."""

    def test_reads_entries_written_by_mark_success(self, tmp_path):
        path = str(tmp_path / "checkpoint.json")
        mark_success({}, "Nhava Sheva", "Singapore", "40HC", path=path)

        checkpoint = load_checkpoint(path)

        assert list(checkpoint.keys()) == ["NHAVA SHEVA|SINGAPORE|40HC"]
        assert checkpoint["NHAVA SHEVA|SINGAPORE|40HC"]["status"] == "success"

    def test_reads_multiple_entries_accumulated_across_calls(self, tmp_path):
        path = str(tmp_path / "checkpoint.json")
        checkpoint = {}
        mark_success(checkpoint, "A", "B", "40HC", path=path)
        mark_success(checkpoint, "C", "D", "20DC", path=path)

        reloaded = load_checkpoint(path)

        assert set(reloaded.keys()) == {"A|B|40HC", "C|D|20DC"}


class TestLoadCheckpointFailPath:
    """load_checkpoint tolerates a missing file, returning {} rather than raising."""

    def test_missing_file_returns_empty_dict(self, tmp_path):
        assert load_checkpoint(str(tmp_path / "does_not_exist.json")) == {}

    def test_file_with_no_entries_key_raises_on_missing_default(self, tmp_path):
        # load_checkpoint uses data.get("entries", {}), so a file with an unrelated
        # top-level shape degrades to {} instead of raising KeyError.
        path = tmp_path / "checkpoint.json"
        path.write_text(json.dumps({"unrelated": "value"}), encoding="utf-8")

        assert load_checkpoint(str(path)) == {}


class TestIsDoneHappyPath:
    """is_done reports True only for combinations recorded with status 'success'."""

    def test_successful_entry_is_done(self):
        checkpoint = {"A|B|40HC": {"status": "success"}}
        assert is_done(checkpoint, "A", "B", "40HC") is True

    def test_lookup_is_case_and_whitespace_insensitive(self):
        checkpoint = {"A|B|40HC": {"status": "success"}}
        assert is_done(checkpoint, " a ", " b ", " 40hc ") is True


class TestIsDoneFailPath:
    """is_done returns False (never raises) for absent, failed, or malformed entries."""

    def test_missing_key_returns_false(self):
        assert is_done({}, "A", "B", "40HC") is False

    def test_failed_entry_is_not_done_and_will_be_retried(self):
        checkpoint = {"A|B|40HC": {"status": "failed"}}
        assert is_done(checkpoint, "A", "B", "40HC") is False

    def test_entry_with_no_status_field_returns_false(self):
        checkpoint = {"A|B|40HC": {}}
        assert is_done(checkpoint, "A", "B", "40HC") is False


class TestMarkSuccessHappyPath:
    """mark_success records a success entry in-memory and persists it to disk immediately."""

    def test_updates_the_in_memory_checkpoint_dict(self, tmp_path):
        checkpoint = {}
        mark_success(checkpoint, "A", "B", "40HC", path=str(tmp_path / "checkpoint.json"))

        assert checkpoint["A|B|40HC"]["status"] == "success"
        assert "scraped_at" in checkpoint["A|B|40HC"]

    def test_persists_to_disk_so_a_reload_sees_it(self, tmp_path):
        path = str(tmp_path / "checkpoint.json")
        mark_success({}, "A", "B", "40HC", path=path)

        assert load_checkpoint(path)["A|B|40HC"]["status"] == "success"

    def test_success_entry_has_no_error_field(self, tmp_path):
        checkpoint = {}
        mark_success(checkpoint, "A", "B", "40HC", path=str(tmp_path / "checkpoint.json"))

        assert "error" not in checkpoint["A|B|40HC"]

    def test_marking_success_after_a_prior_failure_flips_is_done_to_true(self, tmp_path):
        path = str(tmp_path / "checkpoint.json")
        checkpoint = {}
        mark_failed(checkpoint, "A", "B", "40HC", error="timeout", path=path)
        assert is_done(checkpoint, "A", "B", "40HC") is False

        mark_success(checkpoint, "A", "B", "40HC", path=path)
        assert is_done(checkpoint, "A", "B", "40HC") is True


class TestMarkFailedHappyPath:
    """mark_failed records a failed entry (with error message) that stays retryable."""

    def test_updates_the_in_memory_checkpoint_dict_with_error(self, tmp_path):
        checkpoint = {}
        mark_failed(checkpoint, "A", "B", "40HC", error="boom", path=str(tmp_path / "checkpoint.json"))

        assert checkpoint["A|B|40HC"]["status"] == "failed"
        assert checkpoint["A|B|40HC"]["error"] == "boom"

    def test_failed_entries_are_not_done(self, tmp_path):
        checkpoint = {}
        mark_failed(checkpoint, "A", "B", "40HC", error="boom", path=str(tmp_path / "checkpoint.json"))

        assert is_done(checkpoint, "A", "B", "40HC") is False

    def test_persists_to_disk_so_a_reload_sees_the_failure(self, tmp_path):
        path = str(tmp_path / "checkpoint.json")
        mark_failed({}, "A", "B", "40HC", error="boom", path=path)

        reloaded = load_checkpoint(path)
        assert reloaded["A|B|40HC"]["status"] == "failed"
        assert reloaded["A|B|40HC"]["error"] == "boom"


class TestMarkFailedFailPath:
    """mark_failed tolerates an empty/default error message without raising."""

    def test_default_empty_error_omits_error_field(self, tmp_path):
        # _record only sets "error" when the value is truthy, so the default ""
        # is dropped entirely rather than being stored as an empty string.
        checkpoint = {}
        mark_failed(checkpoint, "A", "B", "40HC", path=str(tmp_path / "checkpoint.json"))

        assert "error" not in checkpoint["A|B|40HC"]


class TestCheckpointResumeScenario:
    """End-to-end style check of the resume workflow load→is_done→mark used by main.py."""

    def test_second_run_skips_a_route_marked_successful_by_the_first_run(self, tmp_path):
        path = str(tmp_path / "checkpoint.json")

        # First run: scrape and record success.
        checkpoint = load_checkpoint(path)
        assert is_done(checkpoint, "Nhava Sheva", "Singapore", "40HC") is False
        mark_success(checkpoint, "Nhava Sheva", "Singapore", "40HC", path=path)

        # Second run: fresh process reloads the checkpoint from disk.
        resumed = load_checkpoint(path)
        assert is_done(resumed, "Nhava Sheva", "Singapore", "40HC") is True
