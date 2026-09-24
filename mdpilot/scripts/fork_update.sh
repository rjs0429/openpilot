#!/usr/bin/env bash
# Pulls the device branch onto the device and rebuilds. The local branch keeps the device branch's name,
# which the stock updater follows from then on.
set -e

BRANCH="avante-md-dev-mici"

cd /data/openpilot

git fetch origin "$BRANCH"
git checkout -B "$BRANCH" "origin/$BRANCH"

git submodule sync --recursive
git submodule update --init --recursive

scons -u

sudo reboot
