# Changelog

## 2026.10.24-3

Found the real cause of the 401s. UniFi OS marks its login cookie as Partitioned, and the
Python version in the add-on quietly throws such cookies away, so the add-on never had a
session. It now reads the cookie straight from the response.

## 2026.10.24-2

The login worked but Protect then turned every request down with a 401. The add-on now
sends the session cookie and CSRF token along with each request, the same way the UniFi
web app does. If Protect still says no, the log shows what the console answered.

## 2026.10.24-1

Switched to date-based version numbers: year.month.day, plus a counter for when there's
more than one release on the same day.

The base image is now set in the Dockerfile itself. The Supervisor had started warning
that build.yaml is deprecated.

## 0.1.0

First version. Live view only for now: a grid with all cameras and a fullscreen view per
camera. The go2rtc config is generated from whatever cameras Protect has.
