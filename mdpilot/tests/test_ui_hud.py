import unittest  # noqa: TID251
from unittest import mock  # noqa: TID251

from openpilot.mdpilot.ui import hud

SET_SPEED_NA = 255


class FakeHud:
  """The part of upstream's mici HudRenderer the fork relies on."""

  def __init__(self):
    self.set_speed = SET_SPEED_NA
    self.is_cruise_set = False
    self._engaged = False
    self._set_speed_changed_time = 0.
    self.next_speed = SET_SPEED_NA
    self.drawn = []

  def _update_state(self):
    self.set_speed = self.next_speed
    self.is_cruise_set = 0 < self.set_speed < SET_SPEED_NA

  def _draw_set_speed(self, rect):
    self.drawn.append((self._engaged, self._set_speed_changed_time))


class TestHud(unittest.TestCase):
  def setUp(self):
    self.clock = 100.
    patcher = mock.patch.object(hud, "get_time", lambda: self.clock)
    patcher.start()
    self.addCleanup(patcher.stop)
    self.hud = hud.build(FakeHud)()

  def _set(self, speed):
    self.clock += 1.
    self.hud.next_speed = speed
    self.hud._update_state()

  def test_new_cruise_set_speed_shows_without_steering(self):
    self._set(98.)
    self.hud._draw_set_speed(None)
    self.assertEqual([(True, self.clock)], self.hud.drawn)
    self.assertFalse(self.hud._engaged)
    self.assertEqual(0., self.hud._set_speed_changed_time)

  def test_unchanged_set_speed_does_not_show_again(self):
    self._set(98.)
    shown = self.clock
    self._set(98.)
    self.hud._engaged = True
    self.hud._set_speed_changed_time = self.clock
    self.hud._draw_set_speed(None)
    self.assertEqual([(True, shown)], self.hud.drawn)

  def test_cruise_leaving_does_not_show(self):
    self._set(98.)
    shown = self.clock
    self._set(SET_SPEED_NA)
    self._set(96.)
    self.assertNotEqual(shown, self.hud._md_shown_at)
    self._set(SET_SPEED_NA)
    self.assertEqual(self.clock - 1., self.hud._md_shown_at)
