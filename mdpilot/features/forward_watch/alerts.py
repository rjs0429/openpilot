"""Runs inside selfdrived: shows the "Ready to Go" prompt that forwardwatchd requests while its toggle is on."""
from openpilot.mdpilot import manifest
from openpilot.mdpilot.upstream import Params, messaging
from openpilot.mdpilot.upstream.alerts import AlertSize, AlertStatus, AudibleAlert, Priority, VisualAlert, permanent_alert

TOGGLE = "ForwardWatchEnabled"
PARAM_EVERY = 10  # control frames


class ForwardWatchAlerts:
  @classmethod
  def create(cls, CP):
    return cls() if manifest.enabled("forward_watch") else None

  def __init__(self, params=None):
    self.params = params if params is not None else Params()
    self.sm = messaging.SubMaster(['forwardWatchState'])
    self.enabled = self.params.get_bool(TOGGLE)
    self.frame = 0
    self.ready_alert = permanent_alert("forwardWatchAlert", ("Ready to Go", "Road ahead is clear"), AlertStatus.userPrompt,
                                       AlertSize.mid, Priority.LOW, VisualAlert.none, AudibleAlert.prompt, 0.5)

  def update(self) -> None:
    self.frame += 1
    if self.frame % PARAM_EVERY == 0:
      self.enabled = self.params.get_bool(TOGGLE)
    self.sm.update(0)

  def alerts(self) -> list:
    if self.enabled and self.sm.alive['forwardWatchState'] and self.sm['forwardWatchState'].alertRequested:
      return [self.ready_alert]
    return []
