import unittest  # noqa: TID251

from cereal import car
from openpilot.common.params import Params
from openpilot.mdpilot.features.follow_cruise.alerts import FollowAlerts
from openpilot.mdpilot.features.follow_cruise.card import FollowCard
from openpilot.mdpilot.features.follow_cruise.publisher import FollowPublisher
from openpilot.mdpilot.features.follow_cruise.toggle import TOGGLE, following
from openpilot.mdpilot.tests.features.test_follow_card import PLAN, FakeInterface, FakeSubMaster


class ToggleParams:
  def __init__(self, value):
    self.value = value

  def get(self, key, return_default=False):
    assert key in (TOGGLE, "MdpilotStatus")
    return self.value if key == TOGGLE else None


def car_params():
  CP = car.CarParams.new_message()
  CP.brand = 'avante_md'
  return CP.as_reader()


class TestFollowToggle(unittest.TestCase):
  def test_defaults_to_on(self):
    self.assertTrue(Params().get(TOGGLE, return_default=True))
    self.assertTrue(following(ToggleParams(True)))

  def test_off_leaves_no_planner_and_no_alerts(self):
    self.assertIsNone(FollowPublisher.create(car_params(), ToggleParams(False)))
    self.assertIsNone(FollowAlerts.create(car_params(), ToggleParams(False)))
    self.assertIsNotNone(FollowPublisher.create(car_params(), ToggleParams(True)))
    self.assertIsNotNone(FollowAlerts.create(car_params(), ToggleParams(True)))

  def test_off_sends_no_command_but_shows_the_set_speed(self):
    card = FollowCard(ToggleParams(False))
    card.sm = FakeSubMaster(PLAN)
    CI = FakeInterface()
    card.push_command(CI)
    self.assertIsNone(CI.CC.cmd)

    CS = car.CarState.new_message()
    CS.cruiseState.speed = 25.
    CS.cruiseState.speedCluster = 25.5
    card.update_car_state(CS)
    self.assertAlmostEqual(90., CS.vCruise, places=3)

  def test_settings_toggles_are_known_params(self):
    from openpilot.mdpilot.ui.toggles import TOGGLES
    params = Params()
    for _, param, _, _ in TOGGLES:
      params.get(param)
