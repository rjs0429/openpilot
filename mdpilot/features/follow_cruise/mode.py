"""The cruise mode setting. Each process reads it once at start, so a change applies from the next drive.

Off: the ECO switch never engages the stock cruise. Cruise: it engages the plain stock cruise, which holds its set speed.
Gap assist: the cruise also slows for the lead car and keeps the speed the driver's pedal reaches.
"""
PARAM = "MdCruiseMode"
OFF, CRUISE, GAP_ASSIST = 0, 1, 2
OPTIONS = ("off", "cruise", "gap assist")


def cruise_mode(params) -> int:
  mode = params.get(PARAM, return_default=True)
  return mode if mode in (OFF, CRUISE, GAP_ASSIST) else GAP_ASSIST
