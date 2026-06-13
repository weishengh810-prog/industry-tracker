from datetime import date

from scripts.common import CACHE_DIR, PROJECT_ROOT
from scripts.source_cache import (
    daily_cache_path,
    read_json_cache,
    write_json_cache,
)


def test_daily_cache_path_uses_source_and_date(tmp_path):
    path = daily_cache_path(
        "github",
        cache_dir=tmp_path,
        today=date(2026, 6, 12),
    )

    assert path == tmp_path / "github_2026-06-12.json"


def test_daily_cache_path_defaults_to_project_cache_directory():
    path = daily_cache_path("github", today=date(2026, 6, 12))

    assert CACHE_DIR == PROJECT_ROOT / "data" / "cache"
    assert path == CACHE_DIR / "github_2026-06-12.json"


def test_json_cache_round_trips_unicode(tmp_path):
    path = tmp_path / "cache.json"
    data = {"industry": "人工智能", "count": 3}

    write_json_cache(path, data)

    text = path.read_text(encoding="utf-8")
    assert read_json_cache(path) == data
    assert text == '{\n  "industry": "人工智能",\n  "count": 3\n}'


def test_read_json_cache_ignores_damaged_json(tmp_path):
    path = tmp_path / "damaged.json"
    path.write_text("{not valid json", encoding="utf-8")

    assert read_json_cache(path) is None


def test_read_json_cache_ignores_invalid_utf8(tmp_path):
    path = tmp_path / "invalid-utf8.json"
    path.write_bytes(b'{"value": "\xff"}')

    assert read_json_cache(path) is None


def test_read_json_cache_ignores_missing_file(tmp_path):
    assert read_json_cache(tmp_path / "missing.json") is None


def test_read_json_cache_ignores_non_dict_json(tmp_path):
    path = tmp_path / "list.json"
    path.write_text('["not", "a", "dict"]', encoding="utf-8")

    assert read_json_cache(path) is None


def test_read_json_cache_ignores_os_errors(tmp_path):
    assert read_json_cache(tmp_path) is None


def test_write_json_cache_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "cache" / "source.json"

    write_json_cache(path, {"ok": True})

    assert path.exists()
    assert read_json_cache(path) == {"ok": True}
