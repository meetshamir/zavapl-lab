# Zava Power SRE Agent architecture

## Incident authority

ServiceNow is the single authoritative incident source and lifecycle owner.
The native Azure SRE Agent ServiceNow incident platform ingests incidents
assigned to `Zava Power SRE` and starts the `auto-investigate` response plan.
The response plan passes the triggering record's ServiceNow `sys_id` to
`incident-handler`.

Azure Monitor alerts, Application Insights, Log Analytics, Azure resource
state, deployment history, Datadog, and Dynatrace are evidence sources. They
must not start a second incident lifecycle or cause an agent to create a mirror
ServiceNow record.

```text
ServiceNow incident assigned to Zava Power SRE
                 |
                 v
Native ServiceNow incident platform
                 |
                 v
auto-investigate response plan (triggering sys_id)
                 |
                 v
incident-handler -----> specialist agents
       |                        |
       +---- Azure diagnostic evidence
       |
       +---- native acknowledgement, discussion, resolution
                 |
                 v
The same ServiceNow incident
```

## Native ServiceNow lifecycle

Use only the runtime-native incident tools:

| Phase | Tool | Identifier |
|-------|------|------------|
| Read | `GetServiceNowIncident` | triggering `sys_id` |
| Acknowledge | `AcknowledgeServiceNowIncident` | triggering `sys_id` |
| Update | `PostServiceNowDiscussionEntry` | triggering `sys_id` |
| Resolve | `ResolveServiceNowIncident` | triggering `sys_id` |

The `INC...` number is human-readable display data. Never use it where a
native action expects `sys_id`.

Custom ServiceNow incident create, lookup, work-note, and resolve tools are not
part of this architecture. `CheckWarranty` remains valid because it is an
unrelated IT-support function.

## Agent topology

| Agent | Role |
|-------|------|
| `incident-handler` | Owns triage, acknowledgement, investigation coordination, updates, validation, and resolution |
| `it-support-handler` | Handles user-impact checks, warranty lookup, and communications |
| `vm-ops-agent` | Diagnoses and remediates VM/disk conditions |
| `deployment-validator` | Finds deployment regressions and performs policy-approved rollback |
| `utility-ops-agent` | Produces proactive health reports without creating incidents |

Specialist agents receive the original incident `sys_id`, return evidence to
`incident-handler`, and update only that incident when they use native
ServiceNow tools.

## Response-plan contract

`auto-investigate` is configured with:

- ServiceNow as its source;
- assignment-group scope `Zava Power SRE`;
- `incident-handler` as the handling agent; and
- instructions to acknowledge, investigate, update, validate, and resolve the
  triggering `sys_id`.

The portal configuration is authoritative because connection authorization and
assignment filters are tenant-specific. The repository YAML records the
intended configuration and agent instructions.

## Simulator boundary

The simulator may create a disposable source incident in
`https://dev442167.service-now.com` after the operator explicitly types
`CREATE`. It uses OAuth client credentials from environment variables and
submits the assignment-group `sys_id`. After creation, the simulator stops
managing the lifecycle; native ingestion and the response plan own it.

The simulator never creates incidents during startup, health checks, tests, or
configuration validation. It does not implement a keep-alive login.

## Security boundary

- Use a dedicated, web-service-only ServiceNow integration user.
- Map the OAuth application to that user and grant only required incident,
  field, and reference ACLs.
- Keep client ID and secret in an ignored local environment or secret manager.
- Never place credentials or access tokens in repository files.
- Credentials formerly committed for the retired instance must be immediately
  revoked or rotated. Git history is intentionally not rewritten, so historical
  exposure remains.

See `docs/SERVICENOW-SETUP.md` for administrative setup and validation.
