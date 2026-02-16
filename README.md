# JVC DLA WiFi Bridge

Home Assistant custom integration for controlling a JVC DLA-RS40 projector over an RS232-to-WiFi bridge (SH-B35W / E103-W08).

## Features

- Runs a TCP server in Home Assistant for SH-B35W TCP client connections.
- Sends RS40 commands:
  - power on
  - power off
  - input HDMI1
  - input HDMI2
  - readiness probe (`ready` command)
- Exposes Home Assistant entities:
  - power switch
  - input select
  - ready binary sensor
- Exposes services:
  - `jvc_dla_wifi_bridge.turn_on`
  - `jvc_dla_wifi_bridge.turn_off`
  - `jvc_dla_wifi_bridge.set_hdmi1`
  - `jvc_dla_wifi_bridge.set_hdmi2`

## HACS

This repository is HACS-compatible and publishes `jvc_dla_wifi_bridge.zip` release assets.

## Release packaging

Build release package locally:

```bash
./scripts/package_release.sh
```

Output:

- `dist/jvc_dla_wifi_bridge.zip`
