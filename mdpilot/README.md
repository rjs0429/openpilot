# mdpilot

Fork-only features for the Avante MD. Upstream files only carry the hooks below; everything else lives here
or in `opendbc_repo/opendbc/car/avante_md/`.

## Follow cruise

Lead following on the stock (non-adaptive) cruise: `followplannerd` runs the upstream longitudinal planner
against the driver's set speed and publishes `followPlanMD`; the car port turns the plan into CANCEL / SET /
RES / SET- taps.

| Hook | Upstream file |
|---|---|
| `followPlanMD` message (custom slot 1) | `cereal/custom.capnp`, `cereal/log.capnp`, `cereal/services.py` |
| process list | `system/manager/process_config.py` |
| plan → CarControl, set speed on the HUD | `selfdrive/car/card.py` (`CardExt`) |
| alerts | `selfdrive/selfdrived/selfdrived.py` (`SelfdrivedExt`) |
| `openpilot.mdpilot` import path (device and PC; the hooks above import it at load, so it must be committed) | `openpilot/mdpilot` symlink |

New alerts go through `SelfdrivedExt`, not new `EventName` values: upstream keeps adding events and the
numbers collide.
