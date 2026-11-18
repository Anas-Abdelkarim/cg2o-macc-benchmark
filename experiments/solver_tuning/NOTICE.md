# Provenance

This package replaces the first tuning scripts of this project (kept in `legacy/experiments/tuning_v0` and
`legacy/experiments/tuning_v1`). It keeps their idea of typed parameter domains and explicit experiment adapters;
the MACC search ranges are derived in part from those scripts. Original configuration files are never overwritten
by a study: the base configuration is copied into the study folder.

Optuna, PyYAML and the optional plotting, build and test dependencies are separate third-party packages under
their own licenses; their source is not included here.
