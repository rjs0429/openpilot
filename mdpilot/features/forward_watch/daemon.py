from openpilot.mdpilot.features.forward_watch.watch import ForwardWatch
from openpilot.mdpilot.upstream import Priority, config_realtime_process, messaging


def main() -> None:
  config_realtime_process([0, 1, 2, 3], Priority.CTRL_LOW)

  pm = messaging.PubMaster(['forwardWatchState'])
  sm = messaging.SubMaster(
    ['carState', 'radarState', 'modelV2', 'driverMonitoringState'],
    poll='modelV2',
  )

  fw = ForwardWatch()

  while True:
    sm.update()

    if not sm.updated['modelV2']:
      continue

    fw.update(sm)
    fw.publish(pm)
