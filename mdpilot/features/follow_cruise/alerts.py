"""Runs inside selfdrived: follow cruise alerts.

All alerts are permanent so they show whether or not steering is engaged. The collision alert reuses the
upstream forward collision warning; the others mirror the steering saturation prompt.
"""
from openpilot.mdpilot import manifest
from openpilot.mdpilot.upstream import DT_CTRL, messaging
from openpilot.mdpilot.upstream.alerts import AlertSize, AlertStatus, AudibleAlert, EventName, Priority, VisualAlert, is_mici, \
                                               permanent_alert

ALERT_DECEL_LIMIT = 1
ALERT_COLLISION = 2
PLAN_LOST_TIME = 1.0


def _prompt(name: str, text: tuple[str, str], mici_text: tuple[str, str]):
  return permanent_alert(name, mici_text if is_mici() else text, AlertStatus.userPrompt, AlertSize.mid, Priority.MID,
                         VisualAlert.none, AudibleAlert.promptRepeat, 2.)


class FollowAlerts:
  @classmethod
  def create(cls, CP):
    return cls() if manifest.enabled("follow_cruise") and CP.brand == manifest.BRAND else None

  def __init__(self):
    self.sm = messaging.SubMaster(['followPlanMD'])
    self.alert_level = 0
    self.plan_lost_frames = 0
    self.decel_limit_alert = _prompt("followDecelLimit", ("Take Control", "Cruise Cannot Slow Down Enough"),
                                     ("take control", "cruise can't slow enough"))
    self.plan_lost_alert = _prompt("followUnavailable", ("Take Control", "Cruise Following Unavailable"),
                                   ("take control", "cruise not following"))

  def update_events(self, events, CS) -> None:
    self.sm.update(0)
    plan = self.sm['followPlanMD']
    fresh = self.sm.alive['followPlanMD'] and self.sm.valid['followPlanMD'] and plan.active
    self.alert_level = plan.alertLevel if fresh else 0
    following = CS.cruiseState.speed > 0.
    self.plan_lost_frames = self.plan_lost_frames + 1 if following and not fresh else 0
    if self.alert_level >= ALERT_COLLISION:
      events.add(EventName.fcw)

  def alerts(self) -> list:
    if self.plan_lost_frames * DT_CTRL >= PLAN_LOST_TIME:
      return [self.plan_lost_alert]
    return [self.decel_limit_alert] if self.alert_level == ALERT_DECEL_LIMIT else []
