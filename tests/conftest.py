"""Los tests nunca llaman al ``gh`` real ni al llavero de Windows: dobles en memoria."""
import pytest

from core import cloud_login, gh_status
from core.cloud_fakes import FakeGhRun, MemoryKeyring


@pytest.fixture(autouse=True)
def _offline_credentials():
    previous_gh = gh_status.set_default(gh_status.GhStatus(run=FakeGhRun()))
    previous_kr = cloud_login.set_backend(MemoryKeyring())
    yield
    gh_status.set_default(previous_gh)
    cloud_login.set_backend(previous_kr)
