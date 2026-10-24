# Protect Viewer

Shows your UniFi Protect cameras on a Cameras page in the Home Assistant sidebar. Every
HA user can open it, so nobody else needs a UniFi account or the Protect app.

## Getting started

First make a local user on the UniFi console (Admins & Users) and give it the View Only
role for Protect. A local user, not a UI.com account. The add-on only needs to look.

Next, enable RTSPS on each camera. In Protect, go to the camera's settings, open Advanced,
and switch on High and Medium. High is what you get fullscreen, Medium is used in the grid.
If you set `grid_quality` to `low`, switch on Low instead of Medium.

Then fill in the console address, username and password in the add-on configuration, start
it, and click Cameras in the sidebar.

## Options

`host` is the IP address or hostname of the console.

`username` and `password` are for the local user you just made.

`verify_ssl` checks the console's certificate. Leave it off unless you've put a real
certificate on the console, because the default one is self-signed.

`grid_quality` picks the stream for the grid: `low`, `medium` or `high`. Fullscreen always
uses High if it's enabled.

`cameras` is a list of camera names, if you only want some of them or want them in a certain
order. Leave it empty to get all cameras sorted by name.

`show_stream_type` puts a small RTC or MSE label in the corner of each camera, so you can
see how it's connected. Off by default, it's mostly useful when you're figuring out why
something is slow.

`webrtc_ip` is the address browsers connect to for WebRTC. Normally you leave it empty and
the add-on looks up the address of the HA host by itself.

`log_level` can go to `debug` when something's wrong. It also logs every request then, so
don't leave it on.

## At home and away

At home the video comes in over WebRTC on port 8555 of the HA host, which is about as fast
as it gets. When you're away (through Nabu Casa, for example) that port isn't reachable, and
the player switches to streaming through Home Assistant itself. That's maybe a second
slower but you don't have to set anything up for it.

One catch: the cameras send AAC audio, and WebRTC can't play that. So at home the fullscreen
view has no sound. Away from home it does.

## If something's off

A tile that says RTSP isn't enabled means you missed that camera in the RTSPS step. The
add-on checks Protect every 10 minutes, or restart it if you don't want to wait.

"Login refused" is nearly always the wrong password, or a UI.com account instead of a
local user.
