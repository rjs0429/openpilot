"""Runs inside plannerd, which already subscribes to everything the follow logic reads and holds the solved
trajectory, and publishes followPlanMD next to the upstream longitudinal plan."""
from openpilot.mdpilot import manifest
from openpilot.mdpilot.features.follow_cruise.planner import FollowOutput, FollowPlanner
from openpilot.mdpilot.upstream import messaging


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


class FollowPublisher:
  @classmethod
  def create(cls, CP):
    return cls(CP) if manifest.enabled("follow_cruise") and CP.brand == manifest.BRAND else None

  def __init__(self, CP):
    self.follow = FollowPlanner(CP)
    self.pm = messaging.PubMaster(['followPlanMD'])

  def publish(self, sm, planner) -> None:
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
