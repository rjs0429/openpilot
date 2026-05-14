#!/bin/bash

set -e

cd /data/openpilot

git fetch origin avante-md-release-mici-src
git reset --hard origin/avante-md-release-mici-src

git submodule sync --recursive
git submodule update --init --recursive

if [ "$1" = "build" ]; then
    scons -u
fi

sudo reboot
