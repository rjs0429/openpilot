from openpilot.mdpilot.features.follow_cruise.card import FollowCard
from openpilot.mdpilot.runtime.guard import guarded


def build(Car):
  class CarMd(Car):
    def __init__(self, *args, **kwargs):
      super().__init__(*args, **kwargs)
      self.md_follow = guarded(FollowCard.create, "follow_cruise", "card", self.CP)

    def state_update(self):
      CS, RD = super().state_update()
      self.md_follow.call("update_car_state", CS)
      return CS, RD

    def controls_update(self, CS, CC):
      if self.sm.all_alive(['carControl']):
        self.md_follow.call("push_command", self.CI)
      super().controls_update(CS, CC)

  return CarMd
