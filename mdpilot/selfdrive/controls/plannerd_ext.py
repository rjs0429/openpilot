"""plannerd hook: publish the follow plan next to the upstream longitudinal plan.

It rides along in plannerd because that process already subscribes to everything the follow logic reads
and already holds the solved trajectory.
"""
import cereal.messaging as messaging
from openpilot.mdpilot.selfdrive.controls.lib.follow_planner import FollowOutput, FollowPlanner


def fill_plan(msg, out: FollowOutput) -> None:
  plan = msg.followPlanMD
  plan.active = out.active
  plan.vCruise = float(out.v_cruise)
  plan.vTarget = float(out.v_target)
  plan.aTarget = float(out.a_target)
  plan.coastRequest = out.coast_request
  plan.alertLevel = out.alert_level
  plan.leadLimited = out.lead_limited
  plan.leadValid = out.lead_valid
  plan.dRel = float(out.d_rel)
  plan.vLead = float(out.v_lead)
  plan.aRequired = float(out.a_required)
  plan.aCoastLimit = float(out.a_coast_limit)
  plan.grade = float(out.grade)
  plan.fcw = out.fcw


class PlannerdExt:
  def __init__(self, CP):
    self.enabled = CP.brand == 'avante_md'
    self.follow = FollowPlanner(CP) if self.enabled else None
    self.pm = messaging.PubMaster(['followPlanMD']) if self.enabled else None

  def publish(self, sm, planner) -> None:
    if not self.enabled:
      return

    valid = sm.all_checks(['carState', 'carControl', 'radarState', 'modelV2'])
    if valid:
      out = self.follow.update(sm, planner)
    else:
      self.follow.reset()
      out = FollowOutput()

    msg = messaging.new_message('followPlanMD')
    msg.valid = valid
    fill_plan(msg, out)
    self.pm.send('followPlanMD', msg)
