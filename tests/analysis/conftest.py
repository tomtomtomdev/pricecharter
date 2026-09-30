import pytest

from tests.analysis import synth


@pytest.fixture(scope="session")
def synth_db(tmp_path_factory):
    conn = synth.build(tmp_path_factory.mktemp("synth") / "synth.db")
    yield conn
    conn.close()
