# FutureBit Apollo III for Home Assistant

Work-in-progress custom integration for the FutureBit Apollo III miner. It polls the miner's local GraphQL API (port 5000 by default) and exposes sensors, a miner-online binary sensor, a mining-enabled switch, and generalized fault monitoring from the miner logs.

Unofficial and not affiliated with FutureBit.

## Install
Copy `custom_components/apollo_iii/` into your Home Assistant `/config/custom_components/`, restart, then add **FutureBit Apollo III** under Settings > Devices & services. You need the miner's host, GraphQL port and dashboard password.

## Status
Early development; version history is in [`custom_components/apollo_iii/README.md`](custom_components/apollo_iii/README.md).
