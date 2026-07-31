# Local load and resilience suite

This suite is restricted to the OncoAgent loopback services and the
`oncoagent` Docker network. It uses the repository's existing authenticated
HTTP performance approach because the pinned k6 image is not pulled from an
external registry during local certification.

Configuration is in `config/defaults.json`. Browser API traffic uses the
same-origin Next.js proxy, MCP traffic uses the configured read-only service
identity, and workflow scenarios preserve human review. All correlation
values begin with `loadtest-`.

Every mutating scenario is a dry run unless
`CONFIRM_LOCAL_LOAD_TEST=YES` is present. `make load-all` runs scenarios
sequentially. Generated, sanitized artifacts are written beneath the ignored
`loadtest_outputs/<load_test_id>/` directory.

The JavaScript scenarios are k6-compatible definitions for environments where
the pinned image is already available. The active orchestrator uses the
repository-approved native runner and never pulls an image during a
local-only certification.
