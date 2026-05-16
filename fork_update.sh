#!/bin/bash

set -e

cd /data/openpilot

git fetch origin avante-md-dev-mici
git reset --hard origin/avante-md-dev-mici

git submodule sync --recursive
git submodule update --init --recursive

scons -u

sudo reboot
