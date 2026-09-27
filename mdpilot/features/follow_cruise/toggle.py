"""The settings toggle for lead following. Off, the ECO switch still engages the stock cruise, which then only
holds its speed. Each process reads it once at start, so a change applies from the next drive."""
TOGGLE = "FollowCruiseEnabled"


def following(params) -> bool:
  return bool(params.get(TOGGLE, return_default=True))
