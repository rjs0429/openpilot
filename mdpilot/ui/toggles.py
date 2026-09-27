from openpilot.mdpilot import manifest
from openpilot.mdpilot.upstream.ui import BigParamControl, ui_state

# (title, param, feature, read only when a drive starts)
TOGGLES = (
  ("forward departure alert", "ForwardWatchEnabled", "forward_watch", False),
  ("cruise follows lead car", "FollowCruiseEnabled", "follow_cruise", True),
)


def extend(layout) -> None:
  """Appends the fork's toggles to the mici toggles page."""
  added = []
  for title, param, feature, per_drive in TOGGLES:
    if not manifest.enabled(feature):
      continue
    widget = BigParamControl(title, param)
    if per_drive:
      widget.set_enabled(lambda: not ui_state.started)
    added.append((param, widget))
  if not added:
    return
  layout._scroller.add_widgets([widget for _, widget in added])
  layout._refresh_toggles = tuple(layout._refresh_toggles) + tuple(added)
