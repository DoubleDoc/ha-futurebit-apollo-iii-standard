"""Shared fixtures: a fake Apollo III GraphQL API built from captured responses."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
from unittest.mock import patch

from aiohttp import ClientError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from homeassistant.util import dt as dt_util

from custom_components.apollo_iii.const import DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"
HOST = "192.0.2.50"
PORT = 5000
PASSWORD = "correct-password"
MAC = "aa:bb:cc:dd:ee:01"
URL = f"http://{HOST}:{PORT}/api/graphql"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    yield


class FakeMiner:
    """Answers the integration's GraphQL queries like an Apollo III."""

    def __init__(self) -> None:
        self.password = PASSWORD
        self.mcu = load("mcu")
        self.miner = load("miner")
        self.settings = load("settings")
        self.logs = load("logs")
        self.unreachable = False
        self.updates: list[dict] = []
        self.commands: list[str] = []

    @property
    def stats(self) -> dict:
        return self.miner["Miner"]["stats"]["result"]["stats"][0]

    @property
    def saved(self) -> dict:
        return self.settings["Settings"]["read"]["result"]["settings"]

    async def handle(self, method, url, data):
        if self.unreachable:
            return AiohttpClientMockResponse(method, url, exc=ClientError("unreachable"))
        query, variables = data["query"], data.get("variables") or {}
        return AiohttpClientMockResponse(method, url, json=self.answer(query, variables))

    def answer(self, query: str, variables: dict) -> dict:
        if "login(" in query:
            if variables.get("password") != self.password:
                return {"errors": [{"message": "Invalid password",
                                    "extensions": {"code": "UNAUTHENTICATED"}}]}
            return {"data": {"Auth": {"login": {"result": {"accessToken": "token"}, "error": None}}}}
        if "Mcu" in query:
            return {"data": self.mcu}
        if "Logs" in query:
            return {"data": self.logs}
        if "update(input" in query:
            self.updates.append(variables["input"])
            self.saved.update(variables["input"])
            return {"data": {"Settings": {"update": {"result": {"settings": dict(self.saved)}, "error": None}}}}
        if "Settings" in query:
            return {"data": copy.deepcopy(self.settings)}
        if command := re.search(r"Miner \{ (start|stop|restart) \{", query):
            self.commands.append(command.group(1))
            return {"data": {"Miner": {command.group(1): {"error": None}}}}
        if "Miner" in query:
            # Fresh stats: the integration marks stats stale when `date` stops changing.
            self.stats["date"] = dt_util.now().isoformat(timespec="microseconds")
            return {"data": copy.deepcopy(self.miner)}
        raise AssertionError(f"Unexpected query: {query}")


@pytest.fixture
def fake_miner(aioclient_mock) -> FakeMiner:
    miner = FakeMiner()
    aioclient_mock.post(URL, side_effect=miner.handle)
    aioclient_mock.post(f"http://192.0.2.99:{PORT}/api/graphql", side_effect=miner.handle)
    return miner


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"Apollo III Standard ({HOST})",
        unique_id=MAC,
        data={"host": HOST, "port": PORT, "password": PASSWORD},
    )


@pytest.fixture
def mock_setup_entry():
    with patch("custom_components.apollo_iii.async_setup_entry", return_value=True) as mock:
        yield mock
