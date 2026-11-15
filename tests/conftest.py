from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def app_server():
    from zimam.runtime import ensure_app
    from zimam.settings import load_settings

    settings = load_settings()
    ensure_app(settings)
    yield settings
