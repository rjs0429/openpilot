#!/usr/bin/env python3
from cereal import car
import cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.common.realtime import Priority, config_realtime_process
from openpilot.common.swaglog import cloudlog
from openpilot.mdpilot.selfdrive.controls.lib.follow_planner import FollowOutput, FollowPlanner

INPUTS = ['carState', 'carControl', 'controlsState', 'selfdriveState', 'liveParameters', 'radarState', 'modelV2']


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


def main():
  config_realtime_process(5, Priority.CTRL_LOW)

  params = Params()
  CP = messaging.log_from_bytes(params.get("CarParams", block=True), car.CarParams)
  cloudlog.info("followplannerd got CarParams: %s", CP.brand)

  planner = FollowPlanner(CP)
  pm = messaging.PubMaster(['followPlanMD'])
  sm = messaging.SubMaster(INPUTS, poll='modelV2')

  while True:
    sm.update()
    if not sm.updated['modelV2']:
      continue

    valid = sm.all_checks(['carState', 'carControl', 'controlsState', 'selfdriveState', 'radarState', 'modelV2'])
    out = planner.update(sm) if valid else FollowOutput()
    if not valid:
      planner.reset()

    msg = messaging.new_message('followPlanMD')
    msg.valid = valid
    fill_plan(msg, out)
    pm.send('followPlanMD', msg)


if __name__ == "__main__":
  main()
