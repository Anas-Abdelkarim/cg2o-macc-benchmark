# Migration from tuning.zip

This is a new standalone package with the import name `tuning`. Do not merge its
`src/tuning` directory into the old `experiments/tuning` folder. Create a clean
environment, install the new package, and invoke `python -m tuning` or
`solver-tune`. Existing MACC simulation code can remain in its original project.

| Previous library | Replacement |
| --- | --- |
| `AlgorithmSpec` plus automatic registry imports | A readable study YAML or Python `Study` construction |
| `ParamSpace` | `Space`; `Float`, `Log`, `Int`, `Cat`, `OneMinusLog` retained |
| `optional` removes only a command override | Adapter materializes a config with the key deleted |
| Baseline silently snapped to domain | Original baseline preserved exactly |
| Exempt baseline | Same quality bounds as every candidate |
| `--method bo` | `method: tpe` |
| `--method cd` | `method: coordinate` |
| `--random-refine` | Use random/TPE/DE as a separate study; coordinate has random restarts |
| Matching paper iterations as a default score | Explicit performance metric; no paper-targeting default |
| Promotion to a different case set | Validation union of original and extra cases |
| `--validate-steps 0` inherited config | MACC writes `mpc.loop_size=0` explicitly |
| Deleted candidate folders | Raw artifacts retained by default |
| Old Optuna SQLite file | New core-owned SQLite journal and reconstructed TPE state |
| `best_config.yaml` partial merge | `best_config.json` and MACC `selected_config.yaml` |
| Standalone plot could label a worse candidate best | Plot status comes from final selected report |

Old study databases cannot be resumed by version 2. New fingerprints are required
because baseline semantics, quality rules and experiment identities changed.
Use old results as exploratory evidence, then start a fresh version-2 study.

A parameter `grid` constrains coordinate-search neighbors only. TPE and random
search use the full declared domain. No rounding to three significant digits is
applied to numeric proposals. Logarithmic values may therefore have many digits;
exact executed values are retained for reproduction.

The supplied `bipm_settings.lagrange_multiplier_initial_eq` option was not consumed
by the attached C++ controller; it is omitted from the new BIPM example. The shared
`general_settings.lagrange_multiplier_initial_eq` option would change an ISPD
driver, so it is also excluded from that fixed-trajectory example.

Accuracy tolerances are intentionally absent from the warm/cold IPOPT search
examples. To explore accuracy-speed trade-offs, declare them yourself and label
the result accordingly; it is a different experiment from fixed-accuracy tuning.
