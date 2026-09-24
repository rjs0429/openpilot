"""Fork alerts bypass upstream's EVENTS table, so they get its alert text checks here."""
import json
import os
import unittest  # noqa: TID251

from PIL import Image, ImageDraw, ImageFont

from cereal import car
from openpilot.common.basedir import BASEDIR
from openpilot.mdpilot import manifest
from openpilot.mdpilot.features.follow_cruise.alerts import FollowAlerts
from openpilot.mdpilot.features.forward_watch.alerts import ForwardWatchAlerts
from openpilot.mdpilot.runtime.status_alert import StatusAlert
from openpilot.selfdrive.selfdrived.events import AlertSize

MAX_TEXT_WIDTH = 2160 - 300


class FakeParams:
  def __init__(self, store):
    self.store = store

  def get(self, key):
    return self.store.get(key)

  def get_bool(self, key):
    return True


def fork_alerts():
  CP = car.CarParams.new_message()
  CP.brand = 'avante_md'
  follow = FollowAlerts.create(CP.as_reader())
  every_feature = dict.fromkeys((*manifest.FEATURES, "processes", "ui", "status"), "somewhere")
  status = StatusAlert(FakeParams({"MdpilotStatus": json.dumps(every_feature)}))
  status.update()
  return [follow.decel_limit_alert, follow.plan_lost_alert, ForwardWatchAlerts(FakeParams({})).ready_alert, *status.alerts()]


class TestForkAlertText(unittest.TestCase):
  def test_sizes_match_their_text(self):
    for a in fork_alerts():
      with self.subTest(alert=a.alert_type):
        if a.alert_size == AlertSize.small:
          self.assertTrue(len(a.alert_text_1) > 0 and len(a.alert_text_2) == 0)
        elif a.alert_size == AlertSize.mid:
          self.assertTrue(len(a.alert_text_1) > 0 and len(a.alert_text_2) > 0)
        self.assertGreaterEqual(a.duration, 0.)

  def test_text_fits_the_screen(self):
    fonts_dir = os.path.join(BASEDIR, "selfdrive/assets/fonts")
    fonts = {
      AlertSize.small: [ImageFont.truetype(os.path.join(fonts_dir, "Inter-SemiBold.ttf"), 74)],
      AlertSize.mid: [ImageFont.truetype(os.path.join(fonts_dir, "Inter-Bold.ttf"), 88),
                      ImageFont.truetype(os.path.join(fonts_dir, "Inter-SemiBold.ttf"), 66)],
    }
    draw = ImageDraw.Draw(Image.new('RGB', (0, 0)))
    for a in fork_alerts():
      for i, txt in enumerate((a.alert_text_1, a.alert_text_2)):
        if i >= len(fonts[a.alert_size]):
          break
        left, _, right, _ = draw.textbbox((0, 0), txt, fonts[a.alert_size][i])
        self.assertLessEqual(right - left, MAX_TEXT_WIDTH, f"{a.alert_type}: {txt!r}")
