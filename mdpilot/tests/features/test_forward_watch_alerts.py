import unittest  # noqa: TID251

import cereal.messaging as messaging
from openpilot.mdpilot.features.forward_watch.alerts import PARAM_EVERY, ForwardWatchAlerts
from openpilot.selfdrive.selfdrived.events import ET


class FakeParams:
  def __init__(self, enabled=True):
    self.enabled = enabled

  def get_bool(self, key):
    assert key == "ForwardWatchEnabled"
    return self.enabled


class FakeSubMaster:
  def __init__(self, requested=True, alive=True):
    msg = messaging.new_message('forwardWatchState')
    msg.forwardWatchState.alertRequested = requested
    self.data = {'forwardWatchState': msg.forwardWatchState.as_reader()}
    self.alive = {'forwardWatchState': alive}

  def update(self, timeout=0):
    pass

  def __getitem__(self, s):
    return self.data[s]


def make(params, sm):
  fw = ForwardWatchAlerts(params)
  fw.sm = sm
  return fw


class TestForwardWatchAlerts(unittest.TestCase):
  def test_requested_alert_is_the_ready_prompt(self):
    fw = make(FakeParams(), FakeSubMaster())
    fw.update()
    alerts = fw.alerts()
    self.assertEqual(1, len(alerts))
    self.assertEqual("Ready to Go", alerts[0].alert_text_1)
    self.assertEqual(f"forwardWatchAlert/{ET.PERMANENT}", alerts[0].alert_type)

  def test_quiet_when_not_requested_or_dead(self):
    for sm in (FakeSubMaster(requested=False), FakeSubMaster(alive=False)):
      fw = make(FakeParams(), sm)
      fw.update()
      self.assertEqual([], fw.alerts())

  def test_toggle_is_followed(self):
    params = FakeParams(enabled=False)
    fw = make(params, FakeSubMaster())
    fw.update()
    self.assertEqual([], fw.alerts())
    params.enabled = True
    for _ in range(PARAM_EVERY):
      fw.update()
    self.assertEqual(1, len(fw.alerts()))
