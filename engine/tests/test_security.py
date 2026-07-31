import pytest

from siftlane_engine.config import Settings
from siftlane_engine.security import FetchRejected, SecureHttpClient


@pytest.mark.asyncio
async def test_private_networks_are_rejected(tmp_path):
    client = SecureHttpClient(Settings(data_dir=tmp_path, allow_private_networks=False))
    try:
        with pytest.raises(FetchRejected, match="not publicly routable"):
            await client.fetch("http://127.0.0.1/internal", respect_robots=False)
    finally:
        await client.close()
