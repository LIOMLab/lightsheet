# lightsheet

Lightsheet Microscope Controller — a PyQt5 desktop application that drives a
custom light-sheet fluorescence microscope (PCO camera, NI-DAQmx scan
generation, Zaber stages, Optotune tunable lenses, Toptica iBeam laser).
Single-machine Windows app run by the operator during live experiments.
Originally loosely based on
[mesoSPIM-control](https://github.com/mesoSPIM/mesoSPIM-control), now
substantially diverged and maintained as its own codebase.

## Branch structure

This repository follows a `develop` > `main` git-flow:

> **Post-reconciliation state:** the legacy `master` branch was renamed to
> `main` and deleted from the remote. `main` is now the GitHub default branch.
> `develop` was branched from the `v2022.9` head and carries the active
> modernization work. The `v2022.9` and `auto_focus` branches are retained for
> historical reference.

- **`main`** — holds releasable states. This is the remote default branch on
  GitHub. Tagged releases are cut from `main`. The deployed rig is re-pointed
  to `main` only after a rig smoke test passes.
- **`develop`** — the active integration branch. Ongoing work (including
  phase-by-phase modernization work) lands on `develop` first and is promoted
  to `main` when it is in a releasable state. Branch feature work off
  `develop` and merge it back into `develop`; do not merge feature work
  directly into `main`.
- **`v2022.9`** — the legacy deployed branch. It is preserved as the
  historical record of the deployed state at the start of the modernization
  effort. The `develop` branch was branched from the `v2022.9` head.
- **`auto_focus`** — an older parallel development line (the `dev2022.7` and
  `dev2022.10` merges) that diverged from `v2022.9` at commit `690fa51`. It
  was inspected before the branch reconciliation and **left as-is** — its
  work is largely superseded by `v2022.9`'s independent HAL split, and
  cherry-picking would cause extensive conflicts. It is retained for
  historical reference; do not delete it.

### Recovery point

The annotated tag **`v2022.9-rig-baseline`** marks the deployed state of the
rig at the start of the modernization effort (the `v2022.9` branch head at
the time the tag was created). It is an immutable recovery point — if the
reconciled `main`/`develop` branches ever regress on the rig, the rig can be
re-pointed to this tag to return to the last known-good deployed state:

```bash
git fetch --all --tags
git checkout v2022.9-rig-baseline
```

## Rig re-point procedure

The microscope PC's working copy at
`C:\Users\liomlight\Documents\GitHub\lightsheet` stays on the
`v2022.9-rig-baseline` tag until a rig smoke test on the reconciled
`main`/`develop` branches passes. **Do not re-point the rig until the smoke
test passes** — switching the rig prematurely detaches the only running
deployment from its known-good state.

After the smoke test passes, re-point the rig (run on the rig, never push
from the rig — see `AGENTS.md` §4):

```bash
ssh lightsheet-rig
cd /c/Users/liomlight/Documents/GitHub/lightsheet
git fetch --all --tags
git checkout main
git pull
```

If the smoke test fails, leave the rig on `v2022.9-rig-baseline`, record the
failure, and fix the regression on `develop` before re-attempting the
re-point.

## Running the app

```bash
.venv/bin/lightsheet              # console script (installed by `pip install -e .`)
.venv/bin/python -m lightsheet    # debug fallback
```

Both forms resolve to `lightsheet.__main__:main` and work from any CWD. On
the Mac dev box this starts the GUI with hardware init failing gracefully
(HAL classes catch SDK errors and set `self.error`) — useful for UI/layout
checks, not for real acquisition.

## Development

See `AGENTS.md` for the full instruction set (safety rules, two-environment
model, rig SSH access, test commands, code style, HAL pattern, GUI
conventions). Read it before making changes — the rules exist because
hardware damage and operator injury are real risks on this project, not just
code-quality concerns.
