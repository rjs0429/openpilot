from openpilot.mdpilot.features.follow_cruise.publisher import FollowPublisher
from openpilot.mdpilot.runtime.guard import guarded


def build(LongitudinalPlanner):
  class LongitudinalPlannerMd(LongitudinalPlanner):
    def __init__(self, CP, *args, **kwargs):
      super().__init__(CP, *args, **kwargs)
      self.md_follow = guarded(FollowPublisher.create, "follow_cruise", "plannerd", CP)

    def publish(self, sm, pm):
      super().publish(sm, pm)
      self.md_follow.call("publish", sm, self)

  return LongitudinalPlannerMd
