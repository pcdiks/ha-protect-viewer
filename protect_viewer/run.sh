#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
bashio::log.info "Starting Protect Viewer"
cd /opt/app || exit 1
exec python3 -m protect_viewer
