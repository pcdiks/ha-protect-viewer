# Protect Viewer for Home Assistant

I wanted my UniFi Protect cameras in Home Assistant the way Frigate shows up there: one
page in the sidebar with all the cameras on it, that the whole family can open. The
native UniFi Protect integration never really did that for me, so I made this add-on.

It logs in to the console, picks up the cameras and their RTSPS streams, and plays them
through a bundled [go2rtc](https://github.com/AlexxIT/go2rtc). Nothing gets transcoded, so it's
light on the HA host.

## Installing

Add this repository to Home Assistant (Settings, Add-ons, Add-on Store, the three dots in
the top right, Repositories):

```
https://github.com/pcdiks/ha-protect-viewer
```

Then install Protect Viewer. The Documentation tab of the add-on explains the rest.

## Hacking on it

Everything is in `protect_viewer/`. The backend is a small aiohttp app in
`protect_viewer/app/protect_viewer` and the UI is plain JavaScript in its `www` folder, so
there's nothing to build. You can run it on your own machine like this:

```sh
cd protect_viewer/app
PV_OPTIONS=options.json PV_GO2RTC=/path/to/go2rtc PV_GO2RTC_CONFIG=/tmp/go2rtc.yaml \
  python -m protect_viewer
```

`options.json` takes the same keys as the add-on options.
