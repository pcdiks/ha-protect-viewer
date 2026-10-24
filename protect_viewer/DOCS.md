# Protect Viewer

Live view of your UniFi Protect cameras in the Home Assistant sidebar, for every
Home Assistant user. No UniFi accounts or the native UniFi Protect integration needed.

Streams come straight from Protect and are only repackaged by the bundled
[go2rtc](https://github.com/AlexxIT/go2rtc), so CPU use stays low. Each camera opens one
connection to the console, however many people are watching.

## Setup

1. **Create a local user on the UniFi console.** In UniFi OS, go to Admins & Users and add a
   local-access-only user with the **View Only** role for Protect.
2. **Enable RTSP on each camera.** In Protect, open each camera's Settings → Advanced and
   enable RTSPS for **High** (fullscreen) and **Medium** (grid). With `grid_quality: low`,
   enable **Low** instead of Medium.
3. **Configure the add-on** with the console address and the user from step 1, then start it.
4. **Open "Cameras"** in the sidebar.

## Options

| Option | Description |
| --- | --- |
| `host` | IP address or hostname of the UniFi console. |
| `username`, `password` | The local user from step 1. |
| `verify_ssl` | Verify the console's TLS certificate. Leave off for the default self-signed certificate. |
| `grid_quality` | Stream used in the grid: `low`, `medium` or `high`. Fullscreen always uses High when it is enabled. |
| `cameras` | Camera names to show, in this order. Empty shows all cameras, sorted by name. |
| `webrtc_ip` | IP address browsers use for WebRTC. Empty detects the Home Assistant host address. |
| `log_level` | `debug` also logs every HTTP request. |

## How video reaches the browser

- **At home:** WebRTC on port 8555 (TCP and UDP) of the Home Assistant host, for the lowest latency.
- **Away (Nabu Casa, or any remote Ingress access):** port 8555 is not reachable, so the player
  falls back to MSE over the Ingress websocket. That adds about a second of latency but works
  without extra configuration.

Camera audio is AAC, which only plays over MSE. Over WebRTC the fullscreen view is video only.

## Troubleshooting

- **"RTSP is not enabled for this camera in Protect"**: enable RTSPS for the camera (setup step 2).
  The add-on checks Protect again every 10 minutes, or restart it to pick up the change right away.
- **"Login refused"**: check the username and password, and that the user is a local user, not a
  UI.com account.
