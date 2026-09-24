"""Fork features that were switched off by a failure, shared across processes through the MdpilotStatus param.

Imports params and logging directly rather than through upstream/, so failures are still recorded when the
window itself is what broke. The status clears when the manager restarts.
"""
import contextlib
import fcntl
import json
import os

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

STATUS_PARAM = "MdpilotStatus"
LOCK_NAME = ".mdpilot_status.lock"


def read_status(params) -> dict[str, str]:
  raw = params.get(STATUS_PARAM)
  if not raw:
    return {}
  try:
    status = json.loads(raw)
  except ValueError:
    return {}
  return {str(k): str(v) for k, v in status.items()} if isinstance(status, dict) else {}


def report_failure(feature: str, where: str) -> None:
  cloudlog.exception(f"mdpilot: {feature} switched off in {where}")
  try:
    params = Params()
    with _locked(params):
      status = read_status(params)
      status[feature] = where
      params.put(STATUS_PARAM, json.dumps(status, sort_keys=True), block=True)
  except Exception:
    cloudlog.exception("mdpilot: failed to record status")


@contextlib.contextmanager
def _locked(params):
  """Serializes the read-modify-write across processes; without a usable lock file the write goes ahead unlocked."""
  try:
    lock = open(os.path.join(os.path.dirname(params.get_param_path()), LOCK_NAME), "a")
  except OSError:
    yield
    return
  with lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    yield
