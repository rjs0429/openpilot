from openpilot.mdpilot import manifest
from openpilot.mdpilot.features.follow_cruise import mode
from openpilot.mdpilot.upstream.ui import BigMultiParamToggle, BigParamControl, ui_state

# (title, param, feature, read only when a drive starts)
TOGGLES = (
  ("forward departure alert", "ForwardWatchEnabled", "forward_watch", False),
)
# (title, param, options, feature, read only when a drive starts); the param holds the option's index
CHOICES = (
  ("cruise mode", mode.PARAM, mode.OPTIONS, "follow_cruise", True),
)


def extend(layout) -> None:
  """Appends the fork's settings to the mici toggles page."""
  toggles = []
  widgets = []
  for title, param, feature, per_drive in TOGGLES:
    if not manifest.enabled(feature):
      continue
    widget = BigParamControl(title, param)
    if per_drive:
      widget.set_enabled(lambda: not ui_state.started)
    toggles.append((param, widget))
    widgets.append(widget)
  for title, param, options, feature, per_drive in CHOICES:
    if not manifest.enabled(feature):
      continue
    choice = BigMultiParamToggle(title, param, list(options))
    if per_drive:
      choice.set_enabled(lambda: not ui_state.started)
    widgets.append(choice)
  if not widgets:
    return
  layout._scroller.add_widgets(widgets)
  layout._refresh_toggles = tuple(layout._refresh_toggles) + tuple(toggles)
