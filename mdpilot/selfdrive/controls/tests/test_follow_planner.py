import math

import cereal.messaging as messaging
from cereal import car, log
from openpilot.common.realtime import DT_MDL
from openpilot.mdpilot.selfdrive.controls.lib.coast import coast_decel
from openpilot.mdpilot.selfdrive.controls.lib.follow_planner import (COAST_MIN_DWELL, LEAD_EXIT_TIME, MIN_GAP_M, MIN_GAP_T,
                                                                     REACTION_T, FollowPlanner, LeadFilter, required_decel)

SERVICES = ['carState', 'carControl', 'controlsState', 'selfdriveState', 'liveParameters', 'radarState', 'modelV2']


def make_cp():
  CP = car.CarParams.new_message()
  CP.brand = 'avante_md'
  CP.steerRatio = 14.65
  CP.wheelbase = 2.7
  CP.vEgoStopping = 0.5
  return CP.as_reader()


class Scene:
  def __init__(self, v_ego=22., v_cruise=25., pitch=0.):
    self.msgs = {s: messaging.new_message(s) for s in SERVICES}
    self.cs.vEgo = v_ego
    self.cs.cruiseState.speed = v_cruise
    self.msgs['carControl'].carControl.orientationNED = [0., pitch, 0.]
    self.msgs['selfdriveState'].selfdriveState.personality = log.LongitudinalPersonality.standard
    self.set_lead(None)

  @property
  def cs(self):
    return self.msgs['carState'].carState

  def set_lead(self, d_rel, v_lead=0., prob=0.95):
    lead = self.msgs['radarState'].radarState.leadOne
    lead.status = d_rel is not None
    lead.dRel = d_rel if d_rel is not None else 0.
    lead.vLead = v_lead
    lead.modelProb = prob if d_rel is not None else 0.

  def view(self):
    return {s: getattr(m.as_reader(), s) for s, m in self.msgs.items()}


def run(planner, scene, seconds):
  out = None
  for _ in range(round(seconds / DT_MDL)):
    out = planner.update(scene.view())
  return out


class TestCoast:
  def test_grade_changes_coasting(self):
    flat = coast_decel(25., 0.)
    assert coast_decel(25., 2.) > flat > coast_decel(25., -2.)

  def test_steep_downhill_leaves_a_floor(self):
    assert coast_decel(25., -8.) > 0.

  def test_faster_coasts_harder(self):
    assert coast_decel(30., 0.) > coast_decel(12., 0.)


class TestRequiredDecel:
  def test_not_closing_needs_nothing(self):
    assert required_decel(20., 30., 20.) == 0.
    assert required_decel(20., 30., 25.) == 0.

  def test_inside_the_minimum_gap_is_infinite(self):
    assert math.isinf(required_decel(25., 10., 20.))

  def test_matches_kinematics(self):
    # 5 m/s closing, 20 m of room after the minimum gap and the reaction time
    d_rel = 20. + (MIN_GAP_M + MIN_GAP_T * 15.) + 5. * REACTION_T
    assert abs(required_decel(20., d_rel, 15.) - 25. / 40.) < 1e-6


class TestLeadFilter:
  def _lead(self, status, d_rel=30., v_lead=20., prob=0.95):
    msg = messaging.new_message('radarState').radarState.leadOne
    msg.status = status
    msg.dRel = d_rel
    msg.vLead = v_lead
    msg.modelProb = prob
    return msg.as_reader()

  def test_needs_a_steady_detection(self):
    f = LeadFilter()
    f.update(self._lead(True), 20., DT_MDL)
    assert not f.present
    for _ in range(5):
      f.update(self._lead(True), 20., DT_MDL)
    assert f.present

  def test_far_lead_needs_high_confidence(self):
    f = LeadFilter()
    for _ in range(40):
      f.update(self._lead(True, d_rel=80., prob=0.7), 20., DT_MDL)
    assert not f.present

  def test_brief_dropout_is_bridged(self):
    f = LeadFilter()
    for _ in range(10):
      f.update(self._lead(True), 20., DT_MDL)
    for _ in range(round(LEAD_EXIT_TIME[0] / DT_MDL) - 2):
      f.update(self._lead(False), 20., DT_MDL)
    assert f.present
    for _ in range(3):
      f.update(self._lead(False), 20., DT_MDL)
    assert not f.present


class TestFollowPlanner:
  @staticmethod
  def _lead_msg(status, d_rel=0., v_lead=0.):
    msg = messaging.new_message('radarState').radarState.leadOne
    msg.status = status
    msg.dRel = d_rel
    msg.vLead = v_lead
    msg.modelProb = 0.95 if status else 0.
    return msg.as_reader()

  def test_inactive_without_a_set_speed(self):
    scene = Scene(v_cruise=0.)
    out = run(FollowPlanner(make_cp()), scene, 1.)
    assert not out.active
    assert not out.coast_request

  def test_free_road_follows_the_set_speed(self):
    scene = Scene(v_ego=25., v_cruise=25.)
    out = run(FollowPlanner(make_cp()), scene, 2.)
    assert out.active
    assert abs(out.v_target - 25.) < 0.5
    assert not out.coast_request
    assert out.alert_level == 0

  def test_target_never_exceeds_the_set_speed(self):
    scene = Scene(v_ego=20., v_cruise=25.)
    out = run(FollowPlanner(make_cp()), scene, 2.)
    assert out.v_target <= 25.

  def test_slower_lead_requests_a_coast(self):
    scene = Scene(v_ego=25., v_cruise=25.)
    scene.set_lead(70., 20.)
    out = run(FollowPlanner(make_cp()), scene, 1.5)
    assert out.lead_limited
    assert out.coast_request
    assert out.v_target < 25.

  def test_matched_lead_at_distance_holds_speed(self):
    scene = Scene(v_ego=22., v_cruise=25.)
    scene.set_lead(45., 22.)
    out = run(FollowPlanner(make_cp()), scene, 2.)
    assert not out.coast_request
    assert out.alert_level == 0

  def test_fast_approach_alerts(self):
    scene = Scene(v_ego=25., v_cruise=25.)
    scene.set_lead(40., 18.)
    out = run(FollowPlanner(make_cp()), scene, 1.)
    assert out.alert_level >= 1
    assert out.coast_request

  def test_bridged_dropout_keeps_closing_in(self):
    f = LeadFilter()
    for _ in range(10):
      f.update(self._lead_msg(True, 30., 15.), 20., DT_MDL)
    for _ in range(10):
      f.update(self._lead_msg(False), 20., DT_MDL)
    assert f.present
    assert abs(f.d_rel - (30. - 5. * 10 * DT_MDL)) < 0.5

  def test_imminent_collision_is_level_two(self):
    scene = Scene(v_ego=25., v_cruise=25.)
    scene.set_lead(20., 12.)
    out = run(FollowPlanner(make_cp()), scene, 0.5)
    assert out.alert_level == 2

  def test_coast_released_once_the_lead_pulls_away(self):
    planner = FollowPlanner(make_cp())
    scene = Scene(v_ego=25., v_cruise=25.)
    scene.set_lead(70., 20.)
    assert run(planner, scene, 1.5).coast_request
    scene.cs.vEgo = 20.
    scene.set_lead(90., 26.)
    out = run(planner, scene, COAST_MIN_DWELL + 1.5)
    assert not out.coast_request

  def test_lost_lead_holds_the_target_until_it_is_gone(self):
    planner = FollowPlanner(make_cp())
    scene = Scene(v_ego=20., v_cruise=25.)
    scene.set_lead(35., 20.)
    held = run(planner, scene, 2.).v_target
    scene.set_lead(None)
    out = run(planner, scene, 0.5)
    assert out.lead_valid
    assert out.v_target <= held + 1e-3
    out = run(planner, scene, LEAD_EXIT_TIME[0] + 1.)
    assert not out.lead_valid
    assert out.v_target > held

  def test_close_but_steady_following_is_not_a_collision(self):
    scene = Scene(v_ego=25., v_cruise=25.)
    scene.set_lead(28., 24.)
    out = run(FollowPlanner(make_cp()), scene, 2.)
    assert out.alert_level < 2

  def test_collision_alert_does_not_flicker(self):
    planner = FollowPlanner(make_cp())
    scene = Scene(v_ego=25., v_cruise=25.)
    scene.set_lead(20., 12.)
    assert run(planner, scene, 0.5).alert_level == 2
    scene.set_lead(60., 25.)
    assert run(planner, scene, 0.5).alert_level == 2
    assert run(planner, scene, 1.0).alert_level < 2

  def test_slow_closing_on_a_steep_downhill_does_not_prompt(self):
    scene = Scene(v_ego=25., v_cruise=25., pitch=-0.05)
    scene.set_lead(75., 24.3)
    out = run(FollowPlanner(make_cp()), scene, 3.)
    assert out.alert_level == 0

  def test_downhill_lowers_coasting(self):
    flat = run(FollowPlanner(make_cp()), Scene(v_ego=25.), 1.).a_coast_limit
    downhill = run(FollowPlanner(make_cp()), Scene(v_ego=25., pitch=-0.04), 3.).a_coast_limit
    assert downhill < flat
