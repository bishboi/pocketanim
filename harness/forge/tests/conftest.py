import sys
from pathlib import Path

# `forge` is a package in harness/forge; make it importable from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import os  # noqa: E402

# Narration is Gemini 3.8 Flash-Lite TTS (or Chirp 3 HD), and tests have no Google key: they build silent (the voice tests set a
# mock Google and PANIM_VOICE themselves). Subprocesses inherit it.
os.environ.setdefault("PANIM_VOICE", "silent")
os.environ.setdefault("FORGE_VOICE", "silent")
# Settings from harness/app/.env.local stay out of tests (chirp._env reads it for terminal commands).
os.environ.setdefault("PANIM_ENV_FILE", "")


# The slowest tests: whole lectures rendered and played on the phone renderer (10-40 s each). `scripts/check.sh
# quick` leaves them out (pytest -m "not slow"); `scripts/check.sh` runs everything.
SLOW = {
    "test_free_manim.py::test_a_lecture_with_free_manim_plays_on_the_phone",
    "test_world_maps.py::test_a_world_map_lecture_builds",
    "test_parallel_build.py::test_a_lecture_built_in_windows_plays_the_same",
    "test_pictures_beside_words.py::test_pictures_play_on_the_phone",
    "test_documents.py::test_figure_and_icon_ops_compile",
    "test_readability.py::test_a_map_chapter_is_zoomed_to_its_places_and_wide_without_a_panel",
    "test_motion.py::test_live_ops_export_as_shapes_and_zoom_draws_the_picture_once",
    "test_shared_cache.py::test_parallel_builds_share_the_cache_without_breaking_each_other",
    "test_maps_history.py::test_new_map_ops_export_to_the_phone_as_lines",
    "test_stage.py::test_map_only_when_a_beat_points_at_it",
    "test_llm_path.py::test_model_workers_to_validated_script",
    "test_pictures_more.py::test_an_emblem_that_is_a_picture_not_shapes_is_shown",
    "test_saved_lectures.py::test_a_saved_series_is_listed_downloaded_and_played_by_the_phone",
    "test_pictures_beside_words.py::test_pictures_are_checked_and_resolved",
    "test_world_maps.py::test_maps_draw_india_as_india_does",
    "test_world_maps.py::test_the_compiler_checks_the_region",
    "test_world_maps.py::test_a_map_of_europe_does_not_reach_infinity",
}


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: a whole lecture rendered or played (left out by check.sh quick)")


def pytest_collection_modifyitems(config, items):
    import pytest

    for item in items:
        if item.nodeid.split("/")[-1].split("[")[0] in SLOW:
            item.add_marker(pytest.mark.slow)
