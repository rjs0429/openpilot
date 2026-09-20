"""selfdrived hooks: follow cruise alerts.

All alerts are permanent so they show whether or not steering is engaged. The collision alert reuses the
upstream forward collision warning; the others mirror the steering saturation prompt and go straight to the
AlertManager, so no new event number is needed.
"""
import cereal.messaging as messaging
from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.selfdrived.events import ET, Alert, AlertSize, AlertStatus, AudibleAlert, EventName, Priority, VisualAlert
from openpilot.system.hardware import HARDWARE

ALERT_DECEL_LIMIT = 1
ALERT_COLLISION = 2
PLAN_LOST_TIME = 1.0


def _prompt(name: str, text: tuple[str, str], mici_text: tuple[str, str]) -> Alert:
  alert = Alert(*(mici_text if HARDWARE.get_device_type() == 'mici' else text), AlertStatus.userPrompt, AlertSize.mid,
                Priority.MID, VisualAlert.none, AudibleAlert.promptRepeat, 2.)
  alert.alert_type = f"{name}/{ET.PERMANENT}"
  alert.event_type = ET.PERMANENT
  return alert


class SelfdrivedExt:
  def __init__(self, CP):
    self.enabled = CP.brand == 'avante_md'
    self.sm = messaging.SubMaster(['followPlanMD']) if self.enabled else None
    self.alert_level = 0
    self.plan_lost_frames = 0
    self.decel_limit_alert = _prompt("followDecelLimit", ("Take Control", "Cruise Cannot Slow Down Enough"),
                                     ("take control", "cruise can't slow enough"))
    self.plan_lost_alert = _prompt("followUnavailable", ("Take Control", "Cruise Following Unavailable"),
                                   ("take control", "cruise not following"))

  def update_events(self, events, CS) -> None:
    if not self.enabled:
      return

    self.sm.update(0)
    plan = self.sm['followPlanMD']
    fresh = self.sm.alive['followPlanMD'] and self.sm.valid['followPlanMD'] and plan.active
    self.alert_level = plan.alertLevel if fresh else 0
    following = CS.cruiseState.speed > 0.
    self.plan_lost_frames = self.plan_lost_frames + 1 if following and not fresh else 0
    if self.alert_level >= ALERT_COLLISION:
      events.add(EventName.fcw)

  def alerts(self) -> list[Alert]:
    if self.plan_lost_frames * DT_CTRL >= PLAN_LOST_TIME:
      return [self.plan_lost_alert]
    return [self.decel_limit_alert] if self.alert_level == ALERT_DECEL_LIMIT else []
