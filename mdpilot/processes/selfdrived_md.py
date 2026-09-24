from openpilot.mdpilot.features.follow_cruise.alerts import FollowAlerts
from openpilot.mdpilot.features.forward_watch.alerts import ForwardWatchAlerts
from openpilot.mdpilot.runtime.guard import guarded
from openpilot.mdpilot.runtime.status_alert import StatusAlert


def build(SelfdriveD):
  class SelfdriveDMd(SelfdriveD):
    def __init__(self, *args, **kwargs):
      super().__init__(*args, **kwargs)
      self.md_follow = guarded(FollowAlerts.create, "follow_cruise", "selfdrived", self.CP)
      self.md_forward = guarded(ForwardWatchAlerts.create, "forward_watch", "selfdrived", self.CP)
      self.md_status = guarded(StatusAlert, "status", "selfdrived")

    def _md_events_on(self) -> bool:
      # upstream update_events stops adding events before initialization and in dashcam mode
      return self.initialized and not self.CP.passive

    def update_events(self, CS):
      super().update_events(CS)
      if self._md_events_on():
        self.md_follow.call("update_events", self.events, CS)
        self.md_forward.call("update")
      self.md_status.call("update")

    def update_alerts(self, CS):
      # The AlertManager keeps alerts by type, so adding these before upstream's own changes nothing else.
      alerts = []
      if self._md_events_on():
        alerts += [*self.md_forward.call("alerts", default=[]), *self.md_follow.call("alerts", default=[])]
      alerts += self.md_status.call("alerts", default=[])
      self.AM.add_many(self.sm.frame, alerts)
      super().update_alerts(CS)

  return SelfdriveDMd
