# Deprecated Windows migration assets

These scripts are byte-preserved operational bridges from 1.3.6. They are not packaged in the `predictor_ops` wheel, are not imported by the portable runtime, and may contain historical consumer names. Use only for rollback or controlled one-task-at-a-time migration described in `docs/removed-operations-migration-plan.md`.

Removal condition: every referenced scheduled task invokes the installed `predictor-ops` CLI and has passed two cadences plus its consumer-owned wheel contract. Target removal: 3.0. Do not use these assets for a new deployment.

