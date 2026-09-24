import unittest  # noqa: TID251

import cereal.messaging as messaging
from cereal import car
from openpilot.common.realtime import DT_CTRL
from openpilot.mdpilot.features.follow_cruise.alerts import PLAN_LOST_TIME, FollowAlerts
from openpilot.selfdrive.selfdrived.events import ET, EventName, Events
from openpilot.selfdrive.selfdrived.alertmanager import AlertManager


class FakeSubMaster:
  def __init__(self, level, active=True, alive=True):
    msg = messaging.new_message('followPlanMD')
    msg.followPlanMD.active = active
    msg.followPlanMD.alertLevel = level
    self.data = {'followPlanMD': msg.followPlanMD.as_reader()}
    self.alive = {'followPlanMD': alive}
    self.valid = {'followPlanMD': True}

  def update(self, timeout=0):
    pass

  def __getitem__(self, s):
    return self.data[s]


def carstate(following=True):
  CS = car.CarState.new_message()
  CS.cruiseState.speed = 25. if following else 0.
  return CS.as_reader()


def car_params(brand='avante_md'):
  CP = car.CarParams.new_message()
  CP.brand = brand
  return CP.as_reader()


def make_alerts(level, **kwargs):
  alerts = FollowAlerts.create(car_params())
  alerts.sm = FakeSubMaster(level, **kwargs)
  return alerts


class TestFollowAlerts(unittest.TestCase):
  def test_quiet_without_alert(self):
    fa = make_alerts(0)
    events = Events()
    fa.update_events(events, carstate())
    self.assertEqual(0, len(events))
    self.assertEqual([], fa.alerts())

  def test_decel_limit_is_a_permanent_prompt(self):
    fa = make_alerts(1)
    events = Events()
    fa.update_events(events, carstate())
    self.assertEqual(0, len(events))
    alerts = fa.alerts()
    self.assertEqual(1, len(alerts))
    self.assertEqual(ET.PERMANENT, alerts[0].event_type)

    AM = AlertManager()
    AM.add_many(1, alerts)
    AM.process_alerts(1, {ET.WARNING})
    self.assertIs(alerts[0], AM.current_alert)

  def test_collision_uses_upstream_fcw(self):
    fa = make_alerts(2)
    events = Events()
    fa.update_events(events, carstate())
    self.assertTrue(EventName.fcw in events.names)
    self.assertEqual([], fa.alerts())

  def test_stale_or_inactive_plan_clears_alerts(self):
    for kwargs in ({'alive': False}, {'active': False}):
      fa = make_alerts(2, **kwargs)
      events = Events()
      fa.update_events(events, carstate())
      self.assertEqual(0, len(events))

  def test_lost_plan_while_following_prompts(self):
    fa = make_alerts(0, alive=False)
    frames = round(PLAN_LOST_TIME / DT_CTRL)
    for _ in range(frames - 1):
      fa.update_events(Events(), carstate())
    self.assertEqual([], fa.alerts())
    fa.update_events(Events(), carstate())
    self.assertEqual([fa.plan_lost_alert], fa.alerts())

  def test_lost_plan_is_quiet_when_not_following(self):
    fa = make_alerts(0, alive=False)
    for _ in range(round(2 * PLAN_LOST_TIME / DT_CTRL)):
      fa.update_events(Events(), carstate(following=False))
    self.assertEqual([], fa.alerts())

  def test_other_brands_get_nothing(self):
    self.assertIsNone(FollowAlerts.create(car_params('toyota')))
