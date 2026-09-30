import pytest
from fastapi.testclient import TestClient

from pricecharter.ui.app import create_app
from tests.analysis import synth


@pytest.fixture(scope="session")
def ui_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("ui") / "synth.db"
    synth.build(path).close()
    return path


@pytest.fixture
def client(ui_db):
    with TestClient(create_app(ui_db)) as c:
        yield c


@pytest.fixture(scope="session")
def analyzed_db(tmp_path_factory):
    from pricecharter.analysis.run import analyze, persist

    path = tmp_path_factory.mktemp("ui-analyzed") / "synth.db"
    conn = synth.build(path)
    persist(conn, analyze(conn, model=False))
    conn.close()
    return path
