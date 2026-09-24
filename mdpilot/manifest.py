"""What the fork adds and every place it touches upstream. Read by processes/, features/, ui/ and the tests.
Standard library only: the manager imports it before anything starts."""
import os
from pathlib import Path

BRAND = "avante_md"

# The upstream commit the fork sits on: upstream `zeroelevenone` (v0.11.1 release source). Update on every sync.
UPSTREAM_BASE = "c0ab3550e"

# A switched-off feature is not attached; a process that carries only switched-off features runs as upstream.
FEATURES = {
  "follow_cruise": True,
  "forward_watch": True,
  "lateral_gate": True,
  "power": True,
  "torque_learning": True,
}


# Features whose process entry the manager could not set up, inherited by every process it starts.
OFF_ENV = "MDPILOT_OFF"


def enabled(feature: str) -> bool:
  return FEATURES.get(feature, False) and feature not in os.environ.get(OFF_ENV, "").split(",")


def switch_off(feature: str) -> None:
  off = {f for f in os.environ.get(OFF_ENV, "").split(",") if f}
  os.environ[OFF_ENV] = ",".join(sorted(off | {feature}))


def repo_root() -> Path:
  return next(p for p in Path(__file__).resolve().parents if (p / ".gitmodules").exists())


# The fork's lines inside upstream files: (path from the repo root, line that must appear exactly once). Only these
# files may differ from UPSTREAM_BASE; custom.capnp also carries the fork message structs and pyproject.toml, launch_env.sh
# and .gitmodules their listed lines. Paths are tried as given and under openpilot/, for upstream's move into openpilot/.
HOOKS = (
  (".gitmodules", "url = https://github.com/rjs0429/opendbc.git"),
  (".gitmodules", "branch = avante-md-dev"),
  ("launch_env.sh", 'export FINGERPRINT="${FINGERPRINT:-AVANTE_MD_2012}"'),
  ("pyproject.toml", '  "mdpilot",'),
  ("cereal/custom.capnp", "struct ForwardWatchState @0x81c2f05a394cf4af {"),
  ("cereal/custom.capnp", "struct FollowPlanMD @0xaedffd8f31e7b55d {"),
  ("cereal/log.capnp", "forwardWatchState @107 :Custom.ForwardWatchState;"),
  ("cereal/log.capnp", "followPlanMD @108 :Custom.FollowPlanMD;"),
  ("cereal/services.py", '"forwardWatchState": (True, 20., 10),'),
  ("cereal/services.py", '"followPlanMD": (True, 20., 10),'),
  ("common/params_keys.h", '{"ForwardWatchEnabled", {PERSISTENT, BOOL}},'),
  ("common/params_keys.h", '{"MdpilotStatus", {CLEAR_ON_MANAGER_START, STRING}},'),
  ("system/manager/process_config.py", "from openpilot.mdpilot import hooks as mdpilot_hooks"),
  ("system/manager/process_config.py", "procs = mdpilot_hooks.apply_processes(procs)"),
  ("selfdrive/controls/controlsd.py", "from openpilot.mdpilot import hooks as mdpilot_hooks"),
  ("selfdrive/controls/controlsd.py", "self.md_lat_gate = mdpilot_hooks.LateralGate(self.CP)"),
  ("selfdrive/controls/controlsd.py", "CC.latActive = self.md_lat_gate.allowed(CS, model_v2) and CC.latActive"),
  ("selfdrive/ui/mici/layouts/settings/toggles.py", "from openpilot.mdpilot import hooks as mdpilot_hooks"),
  ("selfdrive/ui/mici/layouts/settings/toggles.py", "mdpilot_hooks.extend_toggles(self)"),
)

# Paths the fork owns outright. Every other change against UPSTREAM_BASE must be a file listed in HOOKS.
FORK_PATHS = ("mdpilot/", "openpilot/mdpilot", "opendbc_repo")
