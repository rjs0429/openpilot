import unittest  # noqa: TID251

from cereal import car
from openpilot.common.params import Params
from openpilot.mdpilot.features.follow_cruise.alerts import FollowAlerts
from openpilot.mdpilot.features.follow_cruise.card import FollowCard
from openpilot.mdpilot.features.follow_cruise.mode import CRUISE, GAP_ASSIST, OFF, PARAM, cruise_mode
from openpilot.mdpilot.features.follow_cruise.publisher import FollowPublisher
from openpilot.mdpilot.tests.features.test_follow_card import PLAN, FakeInterface, FakeSubMaster


class ModeParams:
  def __init__(self, value):
    self.value = value

  def get(self, key, return_default=False):
    assert key in (PARAM, "MdpilotStatus")
    return self.value if key == PARAM else None


def car_params():
  CP = car.CarParams.new_message()
  CP.brand = 'avante_md'
  return CP.as_reader()


class TestCruiseMode(unittest.TestCase):
  def test_defaults_to_gap_assist(self):
    self.assertEqual(GAP_ASSIST, Params().get(PARAM, return_default=True))
    self.assertEqual(GAP_ASSIST, cruise_mode(ModeParams(None)))
    self.assertEqual(GAP_ASSIST, cruise_mode(ModeParams(7)))

  def test_only_gap_assist_plans_and_alerts(self):
    for mode, following in ((OFF, False), (CRUISE, False), (GAP_ASSIST, True)):
      with self.subTest(mode=mode):
        self.assertEqual(following, FollowPublisher.create(car_params(), ModeParams(mode)) is not None)
        self.assertEqual(following, FollowAlerts.create(car_params(), ModeParams(mode)) is not None)

  def test_off_keeps_the_eco_switch_from_engaging(self):
    for mode, enabled in ((OFF, False), (CRUISE, True), (GAP_ASSIST, True)):
      with self.subTest(mode=mode):
        CI = FakeInterface()
        FollowCard(ModeParams(mode), CI)
        self.assertEqual(enabled, CI.CC.cruise_enabled)

  def test_plain_cruise_sends_no_command_but_shows_the_set_speed(self):
    CI = FakeInterface()
    card = FollowCard(ModeParams(CRUISE), CI)
    card.sm = FakeSubMaster(PLAN)
    card.push_command(CI)
    self.assertIsNone(CI.CC.cmd)

    CI.CC.display = 99.6
    CS = car.CarState.new_message()
    CS.cruiseState.speed = 25.
    card.update_car_state(CS)
    self.assertAlmostEqual(90., CS.vCruise, places=3)
    self.assertEqual(100., CS.vCruiseCluster)

  def test_settings_are_known_params(self):
    from openpilot.mdpilot.ui.toggles import CHOICES, TOGGLES
    params = Params()
    for _, param, _, _ in TOGGLES:
      params.get(param)
    for _, param, options, _, _ in CHOICES:
      self.assertLess(params.get(param, return_default=True), len(options))
