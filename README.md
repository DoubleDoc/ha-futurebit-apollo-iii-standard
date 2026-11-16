# FutureBit Apollo III for Home Assistant

Work-in-progress custom integration for the FutureBit Apollo III miner. It polls the miner's local GraphQL API (port 5000 by default) and exposes sensors, a miner-online binary sensor, a mining-enabled switch, and generalized fault monitoring from the miner logs.

Unofficial and not affiliated with FutureBit.

## Install
1. **HACS:** add `https://github.com/DoubleDoc/apollo-iii-integration` as a custom repository (type *Integration*) and install **FutureBit Apollo III**.
   **Manual:** copy `custom_components/apollo_iii/` into your Home Assistant `/config/custom_components/`.
2. Restart Home Assistant.

## Configure
- **Discovery:** Home Assistant usually finds the miner on your network by its hostname (`futurebit-apollo-*`) and offers it under Settings > Devices & services. Click **Add** and enter the dashboard password.
- **Manually:** Settings > Devices & services > Add integration > **FutureBit Apollo III**, then enter:
  - **Host:** the controller's IP address or hostname.
  - **API port:** `5000` unless you changed it.
  - **Dashboard password:** the password for the Apollo web dashboard. The Apollo has no username.
- **Change the IP, port or password later:** open the integration's menu (three dots) > **Reconfigure**. Leave the password blank to keep it.
- **If the dashboard password changes,** Home Assistant shows a re-authentication prompt; enter the new password.
- **If the miner's IP changes,** discovery updates it automatically. Each miner is identified by its controller's MAC address.

For local development, `./deploy.sh` copies the integration into `/config/custom_components/` (backing up the live copy first); restart Home Assistant afterwards.

## Status
Early development; version history is in [`custom_components/apollo_iii/README.md`](custom_components/apollo_iii/README.md).
