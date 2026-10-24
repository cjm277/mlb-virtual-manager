"""The app must find .env in the repo folder first, then in the folder above it."""

import os

import pytest

from backend import config

KEY = config.API_KEY_NAME


@pytest.fixture
def layout(tmp_path, monkeypatch):
    """A fake submissions/ folder with the repo cloned inside it."""
    monkeypatch.delenv(KEY, raising=False)
    repo = tmp_path / "your-project"
    repo.mkdir()
    return (repo / ".env", tmp_path / ".env")


def test_parent_env_is_used_when_repo_has_none(layout):
    repo_env, parent_env = layout
    parent_env.write_text(f"{KEY}=from-parent\n")
    assert config.get_api_key(layout) == "from-parent"


def test_repo_env_wins_over_parent(layout):
    repo_env, parent_env = layout
    repo_env.write_text(f"{KEY}=from-repo\n")
    parent_env.write_text(f"{KEY}=from-parent\n")
    assert config.get_api_key(layout) == "from-repo"


def test_missing_key_stops_with_clear_message(layout):
    with pytest.raises(SystemExit) as stop:
        config.get_api_key(layout)
    assert KEY in str(stop.value)
    assert os.getenv(KEY) is None
