import cereal.messaging as messaging
from cereal import car
from openpilot.common.realtime import DT_CTRL
from openpilot.mdpilot.selfdrive.selfdrived.selfdrived_ext import PLAN_LOST_TIME, SelfdrivedExt
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


def make_ext(level, **kwargs):
  CP = car.CarParams.new_message()
  CP.brand = 'avante_md'
  ext = SelfdrivedExt(CP.as_reader())
  ext.sm = FakeSubMaster(level, **kwargs)
  return ext


class TestSelfdrivedExt:
  def test_quiet_without_alert(self):
    ext = make_ext(0)
    events = Events()
    ext.update_events(events, carstate())
    assert len(events) == 0
    assert ext.alerts() == []

  def test_decel_limit_is_a_permanent_prompt(self):
    ext = make_ext(1)
    events = Events()
    ext.update_events(events, carstate())
    assert len(events) == 0
    alerts = ext.alerts()
    assert len(alerts) == 1
    assert alerts[0].event_type == ET.PERMANENT

    AM = AlertManager()
    AM.add_many(1, alerts)
    AM.process_alerts(1, {ET.WARNING})
    assert AM.current_alert is alerts[0]

  def test_collision_uses_upstream_fcw(self):
    ext = make_ext(2)
    events = Events()
    ext.update_events(events, carstate())
    assert EventName.fcw in events.names
    assert ext.alerts() == []

  def test_stale_or_inactive_plan_clears_alerts(self):
    for kwargs in ({'alive': False}, {'active': False}):
      ext = make_ext(2, **kwargs)
      events = Events()
      ext.update_events(events, carstate())
      assert len(events) == 0

  def test_lost_plan_while_following_prompts(self):
    ext = make_ext(0, alive=False)
    frames = round(PLAN_LOST_TIME / DT_CTRL)
    for _ in range(frames - 1):
      ext.update_events(Events(), carstate())
    assert ext.alerts() == []
    ext.update_events(Events(), carstate())
    assert ext.alerts() == [ext.plan_lost_alert]

  def test_lost_plan_is_quiet_when_not_following(self):
    ext = make_ext(0, alive=False)
    for _ in range(round(2 * PLAN_LOST_TIME / DT_CTRL)):
      ext.update_events(Events(), carstate(following=False))
    assert ext.alerts() == []

  def test_other_brands_do_nothing(self):
    CP = car.CarParams.new_message()
    CP.brand = 'toyota'
    ext = SelfdrivedExt(CP.as_reader())
    events = Events()
    ext.update_events(events, carstate())
    assert ext.sm is None
    assert len(events) == 0
