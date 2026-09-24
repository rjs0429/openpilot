import traceback


def _report(feature: str, where: str) -> None:
  try:
    from openpilot.mdpilot.runtime.health import report_failure
    report_failure(feature, where)
  except Exception:
    traceback.print_exc()


class Guarded:
  """Calls into a feature object. The first exception switches the feature off for this process and reports it;
  after that every call returns its default, so the upstream process carries on as stock."""

  def __init__(self, obj, feature: str, where: str):
    self.obj = obj
    self.feature = feature
    self.where = where

  @property
  def active(self) -> bool:
    return self.obj is not None

  def call(self, method: str, *args, default=None):
    if self.obj is None:
      return default
    try:
      return getattr(self.obj, method)(*args)
    except Exception:
      self.obj = None
      _report(self.feature, self.where)
      return default


def guarded(factory, feature: str, where: str, *args) -> Guarded:
  """Builds a feature object through `factory`. A factory returning None leaves the feature off quietly; one that
  raises leaves it off and reports it."""
  try:
    return Guarded(factory(*args), feature, where)
  except Exception:
    _report(feature, where)
    return Guarded(None, feature, where)
