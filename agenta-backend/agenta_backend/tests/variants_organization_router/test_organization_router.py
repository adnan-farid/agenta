import os

from agenta_backend.services import selectors
from agenta_backend.models.db_models import UserDB
from agenta_backend.models.api.organization_models import OrganizationOutput

import httpx
import pytest


# Initialize http client
test_client = httpx.AsyncClient()
timeout = httpx.Timeout(timeout=5, read=None, write=5)

# Set global variables
ENVIRONMENT = os.environ.get("ENVIRONMENT")
if ENVIRONMENT == "development":
    BACKEND_API_HOST = "http://host.docker.internal/api"
elif ENVIRONMENT == "github":
    BACKEND_API_HOST = "http://agenta-backend-test:8000"


@pytest.mark.asyncio
async def test_list_organizations():
    response = await test_client.get(f"{BACKEND_API_HOST}/organizations/")

    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_get_user_organization():
    user = await UserDB.find_one(UserDB.uid == "0")
    user_org = await selectors.get_user_own_org(user.uid)

    response = await test_client.get(f"{BACKEND_API_HOST}/organizations/own/")

    assert response.status_code == 200
    assert response.json() == OrganizationOutput(
        id=str(user_org.id), name=user_org.name
    )


@pytest.mark.asyncio
async def test_user_does_not_have_an_organization():
    user = UserDB(uid="0123", username="john_doe", email="johndoe@email.com")
    await user.create()

    user_org = await selectors.get_user_own_org(user.uid)
    assert user_org == None
