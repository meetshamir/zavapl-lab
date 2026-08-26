# Azure SRE Agent setup

## 1. Deploy Azure resources

```bash
azd up
bash scripts/post-provision.sh
```

Verify the PowerGrid container apps, Log Analytics workspace, Application
Insights resource, and SRE Agent are available.

## 2. Apply agent resources

```bash
bash scripts/configure-agent.sh
```

The script applies repository agents, skills, knowledge, and the unrelated
warranty tool. It does not create the native ServiceNow incident-platform
connection or response plan because those require tenant-specific portal
authorization.

## 3. Connect ServiceNow

Follow [SERVICENOW-SETUP.md](SERVICENOW-SETUP.md) to configure:

- the `dev442167` least-privilege ServiceNow identities and ACLs;
- OAuth client credentials used only by the demo simulator;
- the native ServiceNow incident platform in SRE Agent;
- assignment-group scoped ingestion; and
- the ServiceNow-source `auto-investigate` response plan.

ServiceNow is the only authoritative incident source. Azure telemetry remains
connected for diagnosis and validation, not for a parallel incident lifecycle.

## 4. Validate end to end

1. Create a disposable incident assigned to `Zava Power SRE`.
2. Wait for native ingestion.
3. Confirm `incident-handler` receives the triggering `sys_id`.
4. Confirm acknowledgement and work notes update the original record.
5. Confirm resolution closes that same record after service health is
   validated.

Never use an `INC...` display number as the native tool identifier. Never
configure custom tools to create or mirror the incident.
