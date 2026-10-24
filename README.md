# Protect Viewer for Home Assistant

A Home Assistant add-on that shows UniFi Protect cameras in the sidebar, with a Frigate-like
UI, without the native UniFi Protect integration.

## Install

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories**.
2. Add `https://github.com/pcdiks/ha-protect-viewer`.
3. Install **Protect Viewer** and follow its Documentation tab.

## Development

The add-on lives in [`protect_viewer/`](protect_viewer). The backend is Python (aiohttp) in
`protect_viewer/app/protect_viewer`, and the UI is plain ES modules in its `www` folder; there is
no build step. To run it outside Home Assistant:

```sh
cd protect_viewer/app
PV_OPTIONS=options.json PV_GO2RTC=/path/to/go2rtc PV_GO2RTC_CONFIG=/tmp/go2rtc.yaml \
  python -m protect_viewer
```

`options.json` uses the same keys as the add-on options.
