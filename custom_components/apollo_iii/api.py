"""Local GraphQL client for Apollo III."""
import asyncio
import time
import logging
from aiohttp import ClientError, ClientSession

_LOGGER = logging.getLogger(__name__)

class ApolloAPIError(Exception):
    """API or GraphQL failure."""

class ApolloAPI:
    def __init__(self, session: ClientSession, host: str, port: int, password: str):
        self.session = session
        self.url = f"http://{host}:{port}/api/graphql"
        self.password = password
        self.token = None
        self._lock = asyncio.Lock()
        # Monotonic time of the last setting change or miner command sent from HA.
        self.last_write = None

    async def _request(self, query, variables=None, *, auth=True, retry=True, read_only=True):
        if auth and not self.token:
            await self.login()
        headers = {"Authorization": f"Bearer {self.token}"} if auth else {}
        try:
            async with self.session.post(
                self.url, json={"query": query, "variables": variables or {}},
                headers=headers, timeout=15
            ) as response:
                response.raise_for_status()
                payload = await response.json()
        except (ClientError, asyncio.TimeoutError) as err:
            # Retry one transient transport failure; never retry a GraphQL
            # application error or a command whose effect is uncertain.
            if retry and read_only:
                await asyncio.sleep(0.5)
                return await self._request(query, variables, auth=auth, retry=False, read_only=read_only)
            raise ApolloAPIError(f"GraphQL transport error: {err}") from err
        except ValueError as err:
            raise ApolloAPIError(f"GraphQL response error: {err}") from err
        errors = payload.get("errors") or []
        if errors:
            if auth and retry and any(
                e.get("extensions", {}).get("code") == "UNAUTHENTICATED" for e in errors
            ):
                self.token = None
                return await self._request(query, variables, auth=True, retry=False)
            raise ApolloAPIError("; ".join(e.get("message", "GraphQL error") for e in errors))
        return payload.get("data") or {}

    async def login(self):
        async with self._lock:
            if self.token:
                return
            data = await self._request(
                """query($password:String!) {
                  Auth { login(input:{password:$password}) {
                    result { accessToken } error { message }
                  }}
                }""",
                {"password": self.password}, auth=False
            )
            response = data.get("Auth", {}).get("login") or {}
            if response.get("error"):
                raise ApolloAPIError(response["error"].get("message", "Login failed"))
            self.token = (response.get("result") or {}).get("accessToken")
            if not self.token:
                raise ApolloAPIError("Login returned no access token")

    @staticmethod
    def unwrap(data, root, field):
        response = (data.get(root) or {}).get(field) or {}
        if response.get("error"):
            raise ApolloAPIError(response["error"].get("message", "Unknown API error"))
        return response.get("result") or {}

    async def get_mcu(self):
        data = await self._request("""{
          Mcu { stats { result { stats {
            timestamp hostname operatingSystem uptime loadAverage architecture
            temperature minerTemperature minerFanSpeed
            memory { total available used cache swap }
            cpu { threads usedPercent }
            disks { total used mountPoint }
            network { name address mac }
          }} error { message } }}
        }""")
        return self.unwrap(data, "Mcu", "stats").get("stats") or {}


    async def get_miner(self):
        data = await self._request("""{
          Miner {
            online { result { online { timestamp status }} error { message }}
            stats { result { stats {
              uuid version date comport statVersion
              master { upTime diff boards errorSpi osc hwAddr boardsI boardsW wattPerGHs
                intervals {
                  int_0 { name interval bySol byDiff byPool byJobs
                    solutions errors errorRate chipSpeed chipRestarts }
                  int_30 { bySol errorRate chipSpeed }
                  int_300 { bySol errorRate }
                  int_3600 { bySol byPool errorRate chipSpeed } } }
              temperature { count min avr max }
              fans { int_0 { rpm } }
              pool { host port userName diff intervals { int_0 {
                jobs sharesSent sharesAccepted sharesRejected solutionsAccepted
                staleJobShares duplicateShares lowDifficultyShares reconnections
              }}}
              slots { int_0 { revision spiNum pwrOn pwrOnTarget temperature
                temperature1 currents solutions errors ghs errorRate chipRestarts
                wattPerGHs osc } }
            }} error { message }}
          }
        }""", auth=False)
        online = self.unwrap(data, "Miner", "online").get("online") or {}
        stats = self.unwrap(data, "Miner", "stats").get("stats") or []
        return {"online": online, "stats": stats}

    async def get_settings(self):
        data = await self._request("""{
          Settings { read { result { settings {
            minerMode minerHashrate voltage frequency fan fan_low fan_high
            fanTemp fanPwm apiAllow customApproval temperatureUnit
          }} error { message } }}
          Services { stats(input:{serviceName:"miner"}) {
            result { data { id serviceName status requestedStatus requestedAt lastChecked }}
            error { message }
          }}
        }""")
        return {
            "settings": self.unwrap(data, "Settings", "read").get("settings") or {},
            "services": self.unwrap(data, "Services", "stats").get("data") or [],
        }

    async def update_settings(self, changes):
        self.last_write = time.monotonic()
        data = await self._request(
            """query($input:SettingsUpdateInput!) {
              Settings { update(input:$input) {
                result { settings { minerMode minerHashrate fanTemp fanPwm } }
                error { message }
              }}
            }""", {"input": changes}, read_only=False
        )
        return self.unwrap(data, "Settings", "update")

    async def miner_command(self, command):
        if command not in ("start", "stop", "restart"):
            raise ValueError("Invalid miner command")
        self.last_write = time.monotonic()
        data = await self._request(
            f"{{ Miner {{ {command} {{ error {{ message }} }} }} }}", read_only=False
        )
        response = (data.get("Miner") or {}).get(command) or {}
        if response.get("error"):
            raise ApolloAPIError(response["error"].get("message", "Command failed"))

    async def get_miner_logs(self):
        """Read authenticated miner log; no service actions."""
        data = await self._request(
            """query LOGS_READ($input: LogReadInput!) {
              Logs { read(input: $input) {
                result { content timestamp }
                error { message type severity }
              }}
            }""",
            {"input": {"logType": "MINER", "lines": 1000}},
        )
        return self.unwrap(data, "Logs", "read")
