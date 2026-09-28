"""The onroad set speed belongs to the cruise: it shows for a moment whenever the cruise's set speed appears or
changes, whether or not openpilot steers, and no longer when steering engages."""
from openpilot.mdpilot.upstream.ui import get_time


def build(HudRenderer):
  class HudRendererMd(HudRenderer):
    def __init__(self, *args, **kwargs):
      super().__init__(*args, **kwargs)
      self._md_shown_at = 0.
      self._md_set_speed = self.set_speed
      self._md_failed = False

    def _update_state(self) -> None:
      super()._update_state()
      if self.set_speed != self._md_set_speed:
        self._md_set_speed = self.set_speed
        if self.is_cruise_set:
          self._md_shown_at = get_time()

    def _draw_set_speed(self, rect) -> None:
      if self._md_failed:
        return super()._draw_set_speed(rect)
      # Upstream draws it only while engaged and times it from its own change: lend it the cruise's instead.
      engaged, changed = self._engaged, self._set_speed_changed_time
      try:
        self._engaged, self._set_speed_changed_time = True, self._md_shown_at
        super()._draw_set_speed(rect)
      except Exception:
        self._md_failed = True
        from openpilot.mdpilot.hooks import report
        report("ui", "hud")
      finally:
        self._engaged, self._set_speed_changed_time = engaged, changed

  return HudRendererMd
