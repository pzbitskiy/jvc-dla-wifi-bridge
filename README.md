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

## SH-B35W serial settings

Set the serial side of SH-B35W to match the projector:

- `19200` baud
- `8` data bits
- `N` parity
- `1` stop bit

A baud mismatch can cause the integration to appear connected while projector commands do nothing.

## Troubleshooting

### Integration loaded but no control/no logs

1. Enable logs in `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.jvc_dla_wifi_bridge: info
```

2. In integration options, set `log_traffic: true`.
3. Restart Home Assistant.
4. Check for these log lines:
   - `Listening for SH-B35W TCP client on ...`
   - `SH-B35W client connected: ...`
   - `TX ...` and `RX ...`

If `SH-B35W client connected` does not appear, SH-B35W is not reaching Home Assistant.

### Device connected but commands do nothing

Check SH-B35W serial config first. The most common cause is baud mismatch.

Required RS40 serial config: `19200 8N1`.

Also verify SH-B35W is in TCP Client mode and points to the Home Assistant host IP and configured integration port.

## Release packaging

Build release package locally:

```bash
./scripts/package_release.sh
```

Output:

- `dist/jvc_dla_wifi_bridge.zip`
