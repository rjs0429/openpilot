from openpilot.mdpilot.runtime.health import read_status
from openpilot.mdpilot.upstream import Params
from openpilot.mdpilot.upstream.alerts import AlertSize, AlertStatus, AudibleAlert, Priority, VisualAlert, is_mici, permanent_alert

CHECK_EVERY = 100  # control frames
MAX_TEXT = 40


class StatusAlert:
  """Tells the driver which fork features a failure switched off."""

  def __init__(self, params=None):
    self.params = params if params is not None else Params()
    self.frame = 0
    self.alert = None

  def update(self) -> None:
    if self.frame % CHECK_EVERY == 0:
      off = sorted(read_status(self.params))
      self.alert = None
      if off:
        title = "md features off" if is_mici() else "MD Features Off"
        names = ", ".join(off)
        if len(names) > MAX_TEXT:
          names = names[:MAX_TEXT - 3] + "..."
        self.alert = permanent_alert("mdpilotStatus", (title, names), AlertStatus.normal, AlertSize.mid,
                                     Priority.LOWER, VisualAlert.none, AudibleAlert.none, 0.)
    self.frame += 1

  def alerts(self) -> list:
    return [self.alert] if self.alert is not None else []
