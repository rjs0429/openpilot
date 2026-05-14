#!/usr/bin/env bash
set -e
set -x

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"
SOURCE_DIR="$(git -C "$DIR" rev-parse --show-toplevel)"

if [ -z "$RELEASE_BRANCH" ]; then
  RELEASE_BRANCH="avante-md-release-mici"
fi

if [ -z "$RELEASE_REMOTE" ]; then
  RELEASE_REMOTE="git@github.com:rjs0429/openpilot.git"
fi

if [ -z "$BUILD_DIR" ]; then
  BUILD_DIR="/data/openpilot-release"
fi

# Personal forks do not have comma's release signing certs.
if [ -z "${PANDA_DEBUG_BUILD+x}" ]; then
  export PANDA_DEBUG_BUILD=1
fi

source "$DIR/identity.sh"

echo "[-] Setting up fork release repo T=$SECONDS"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
git init
git remote add origin "$RELEASE_REMOTE"
git checkout --orphan "$RELEASE_BRANCH"

echo "[-] copying release files T=$SECONDS"
cd "$SOURCE_DIR"
cp -pR --parents $(./release/release_files.py) "$BUILD_DIR/"

cd "$BUILD_DIR"

rm -f panda/board/obj/panda.bin.signed
rm -f panda/board/obj/panda_h7.bin.signed

VERSION=$(cat common/version.h | awk -F[\"-] '{print $2}')
echo "[-] committing version $VERSION T=$SECONDS"
git add -f .
git commit -a -m "openpilot v$VERSION fork release"

export PYTHONPATH="$BUILD_DIR"
op build

if [ "$PANDA_DEBUG_BUILD" = "1" ]; then
  scons panda/
else
  CERT=/data/pandaextra/certs/release RELEASE=1 scons panda/
fi

if test "$(git submodule--helper list | wc -l)" -gt "0"; then
  echo "submodules found:"
  git submodule--helper list
  exit 1
fi
git submodule status

find . -name '*.a' -delete
find . -name '*.o' -delete
find . -name '*.os' -delete
find . -name '*.pyc' -delete
find . -name 'moc_*' -delete
find . -name '__pycache__' -delete
rm -rf .sconsign.dblite Jenkinsfile release/
rm -f selfdrive/modeld/models/*.onnx

find third_party/ -name '*x86*' -exec rm -r {} +
find third_party/ -name '*Darwin*' -exec rm -r {} +

git checkout third_party/

touch prebuilt

git add -f .
git commit --amend -m "openpilot v$VERSION fork release"

RELEASE=1 pytest -n0 -s selfdrive/test/test_onroad.py

echo "[-] pushing $RELEASE_BRANCH to $RELEASE_REMOTE T=$SECONDS"
git push -f origin "$RELEASE_BRANCH:$RELEASE_BRANCH"

echo "[-] done T=$SECONDS"
