# mdpilot

Everything this fork adds on top of upstream openpilot, for the 2012 Hyundai Avante MD. The car port itself lives in
`opendbc_repo/opendbc/car/avante_md/` (see its README).

## Layout

| Path | What |
|---|---|
| `manifest.py` | Feature switches, the fork's lines in upstream files (`HOOKS`), the upstream base commit |
| `hooks.py` | The only fork module upstream files import. Standard library only; falls back to stock on failure |
| `upstream/` | Where features and ui reach upstream. `contract.py` checks what the fork assumes about upstream |
| `processes/` | Attach points: swap an upstream class (card, plannerd, selfdrived) or patch module values (torqued, hardwared), then run upstream `main()`. These may touch upstream directly |
| `features/` | The features. They import upstream only through `upstream/` |
| `runtime/` | Failure isolation (`guard.py`), the `MdpilotStatus` record (`health.py`) and its alert |
| `ui/` | Toggles added to the mici settings page |
| `scripts/fork_update.sh` | Resets `/data/openpilot` to the device branch, builds and reboots the device |
| `tests/` | `unittest.TestCase` only |

## Features

| Feature | Where it runs | How it attaches |
|---|---|---|
| `follow_cruise` | plannerd, card, selfdrived + the car port | class swap; the plan reaches the port through `CarController.set_follow_command`, valid for one cycle |
| `forward_watch` | own process `forwardwatchd` + selfdrived | new process; alert added straight to the AlertManager |
| `lateral_gate` | controlsd | `hooks.LateralGate` (controlsd decides and uses `latActive` in one method, so it keeps a 3-line hook) |
| `power` | hardwared | overrides `power_monitoring` values before upstream `main()` |
| `torque_learning` | torqued | adds the brand to `ALLOWED_CARS` before upstream `main()` |

Other fork settings: `launch_env.sh` fixes `FINGERPRINT`; `.gitmodules` points opendbc at the fork. Swapped processes run
under the fork module's process title.

## Rules

1. Fork code goes under `mdpilot/` or the car port. No new files in upstream directories.
2. Features reach upstream only through `upstream/`; add every new assumption to `upstream/contract.py`.
3. Never append to shared numbering: no new `EventName`, `SafetyModel` or CarState/CarControl fields. Use the
   `custom.capnp` reserved slots for messages and `upstream.alerts.permanent_alert` for alerts.
4. Never repurpose a field upstream gives a meaning. Hand values to the car port through its own methods.
5. Attach in this order of preference: a new process, an attach point in `processes/`, a hook in `hooks.py`. Never
   copy an upstream method body.
6. Modules the manager pre-imports (`hooks.py`, `manifest.py`, `processes/*.py` entries) import only the standard
   library (and `manifest.py`) at the top. If a process entry is missing or cannot be set up when the manager builds
   its process list, its features are switched off in every process. Failures inside a process (attaching, or a
   feature call through `runtime.guard`; `hooks.LateralGate` for the lateral gate) leave that process stock for the
   feature and record it in `MdpilotStatus` (cleared when the manager restarts); the fork's selfdrived shows it as an
   alert. Once `follow_cruise` is recorded off, card stops handing commands to the car, so the car stops following.
7. Only the files in `manifest.HOOKS` may differ from upstream, and each listed line must be there once;
   `tests/test_hooks.py` enforces both.
8. Signals decoded by both the port and panda safety need an agreement test (see the port README for what is
   covered); new CAN transmits need a safety test.

## Tests

```
pytest mdpilot/tests                                   # fork, contract, hooks, fallback
python -m unittest discover -s mdpilot/tests -t .      # how upstream's unittest runner finds them
cd opendbc_repo && pytest -n0 opendbc/car/avante_md/tests opendbc/safety/tests/test_avante_md.py
cd opendbc_repo && rm -f opendbc/safety/tests/libsafety/tmp* && ./opendbc/safety/tests/test.sh
```

The last line is upstream's full safety suite with its 100% line coverage gate, required of forks that change safety
code (`docs/SAFETY.md`). Old `libsafety/tmp*` builds of a changed header break its coverage merge, hence the `rm`.

## Following upstream

0. First time only: squash each fork into one commit on its base (`manifest.UPSTREAM_BASE` for openpilot, the pinned
   opendbc commit for opendbc). The older fork history edits upstream files this layout no longer touches.
1. opendbc: rebase the fork commits onto the opendbc commit the new upstream release pins
   (`git ls-tree <upstream-release-source> opendbc_repo`). Mirror what upstream changed in `opendbc/car/hyundai/`,
   then pass the full safety suite (see Tests).
2. openpilot: rebase from `manifest.UPSTREAM_BASE` onto the new upstream release source branch (`zeroelevenone`,
   `zeroeleventwo`, ...), e.g. `git rebase --onto commaai/zeroeleventwo c0ab3550e`. Name the old base: each release
   branch carries its own reverts, and a plain rebase replays them onto the new release. Conflicts should be limited
   to the `manifest.HOOKS` files.
3. Run `tests/test_contract.py` first and fix what it names in `upstream/` or `processes/`.
4. Build with every `manifest.FEATURES` switch off (stock upstream), then switch features on one at a time.
5. Update `manifest.UPSTREAM_BASE`. Test on the device from a separate branch before `avante-md-dev-mici`, which the
   device updates from on its own.

Moving to v0.11.2, where upstream code lives under `openpilot/`:
- move `mdpilot/` to `openpilot/mdpilot/`, drop the symlink and the `pyproject.toml` hook, and re-add the
  `process_config.py` hook lines in `openpilot/system/manager/` (git leaves the root copy as a modify/delete);
- in `upstream/` and the tests: `openpilot.cereal` and `openpilot.common.hardware` imports; `get_accel_from_plan` takes
  no `vEgoStopping` and returns a number, and `CarParams.vEgoStopping` is deprecated (`upstream/planner.py`, contract
  `FIELDS` and `check_planner`); leads use `present` instead of `status` (`upstream.lead_present`, contract `FIELDS`);
- remove the `# noqa: TID251` markers;
- in the port: `FwQueryConfig` needs `fw_version_regex`, and `CarState.brake` is gone.
