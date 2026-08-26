# SRE Agent configuration

Run `bash scripts/configure-agent.sh` after `azd up`, or apply the resources
manually in [Azure SRE Agent](https://sre.azure.com).

## Repository resources

Apply these five agents:

```bash
for file in sre-config/agents/*.yaml; do
  srectl apply-yaml --file "$file"
done
```

Apply the legitimate custom warranty tool:

```bash
srectl apply-yaml --file sre-config/tools/CheckWarranty/CheckWarranty.yaml
```

Apply all seven skills:

```bash
for skill in \
  outage-api-diagnosis \
  meter-api-diagnosis \
  grid-status-diagnosis \
  notification-svc-diagnosis \
  deployment-rollback \
  disk-space-cleanup \
  servicenow-incident-mgmt
do
  srectl skill apply --name "$skill"
done
```

Upload the knowledge documents:

```bash
for file in knowledge-base/*.md; do
  srectl doc upload --file "$file"
done
```

The repository intentionally does not contain custom ServiceNow incident
create, lookup, work-note, or resolve tools. Do not recreate or reapply them.
The runtime-native tools are:

- `GetServiceNowIncident`
- `AcknowledgeServiceNowIncident`
- `PostServiceNowDiscussionEntry`
- `ResolveServiceNowIncident`

All four accept the triggering incident's ServiceNow `sys_id`, not its
`INC...` display number.

## Required portal configuration

CLI-applied agents and skills are not sufficient. Complete
[SERVICENOW-SETUP.md](SERVICENOW-SETUP.md):

1. Connect `https://dev442167.service-now.com` as the native ServiceNow
   incident platform.
2. Scope ingestion to the `Zava Power SRE` assignment group.
3. Create or update `auto-investigate` as a ServiceNow-source response plan.
4. Select `incident-handler` as the handling agent.
5. Ensure the plan preserves the triggering `sys_id` through acknowledgement,
   discussion updates, and resolution.

Azure Monitor, App Insights, Log Analytics, deployment data, and Azure resource
state are investigation tools only. They are not an authoritative incident
source for this response plan.

## Agent responsibilities

| Agent | Responsibility |
|-------|----------------|
| `incident-handler` | Owns the native ServiceNow incident investigation and lifecycle |
| `it-support-handler` | Handles user-impact and warranty/email tasks while updating the same incident |
| `vm-ops-agent` | Diagnoses VM/disk issues and updates the same incident |
| `deployment-validator` | Correlates and rolls back deployments; never creates a duplicate incident |
| `utility-ops-agent` | Produces scheduled health reports without opening an incident lifecycle |

Reapply repository configuration and reconnect the native incident platform
after agent schema, connector credentials, ACLs, or ServiceNow assignment
records change.
