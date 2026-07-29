# Security retention and deletion

Retention policy is source controlled in `app.security.retention`. The
default operation is a dry run:

```sh
make retention-dry-run
```

The report identifies categories, durations, rationale, owners, and hold
behavior. It does not delete audit records, workflow evidence, Temporal
history, or synthetic data. Any future deletion command must name a category
and bounded date range, show a dry-run preview, require explicit confirmation,
be authorized by application policy, and create an access-decision audit
record. This is not legal advice or a production retention claim.
