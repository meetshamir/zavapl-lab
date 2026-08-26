# ServiceNow setup

Zava Power uses `https://dev442167.service-now.com` as the ServiceNow developer
instance. ServiceNow is the authoritative incident source and lifecycle owner.
Azure Monitor, Application Insights, Log Analytics, and Azure resources provide
diagnostic evidence; they do not create a parallel incident lifecycle.

> **Security notice:** Credentials committed for the retired instance are
> compromised. Revoke or rotate them immediately. This repository does not
> rewrite history, so those values remain exposed in historical commits. Never
> reuse them and never put ServiceNow credentials in YAML, documentation, source
> code, command history, or screenshots.

## 1. Prepare the developer instance

1. Wake `dev442167` in the ServiceNow Developer Portal and confirm the instance
   is reachable.
2. In ServiceNow, create an assignment group named `Zava Power SRE`.
3. Create or verify any referenced records used by incidents:
   - users who may be assigned incidents;
   - the `Zava Power SRE` group and its membership;
   - configuration items for the PowerGrid services, if the integration sets
     `cmdb_ci`;
   - allowed category/subcategory values.
4. Do not configure a scripted keep-alive or headless browser login. Developer
   instances can sleep and must be resumed through supported ServiceNow
   administration.

The simulator sends the assignment group **`sys_id`**, not its display name.
Copy that value from the group record URL and set it only in the local
environment.

## 2. Create the least-privilege integration identity

1. Create a dedicated user such as `zava_sre_integration`.
2. Mark it **Web service access only** and do not grant `admin`.
3. Create a dedicated role, for example `x_zava_sre.integration`, and assign it
   to that user.
4. Grant only the access required by the two consumers:

   | Operation | Required access |
   |-----------|-----------------|
   | Simulator | Create `incident`; write `short_description`, `description`, `category`, `impact`, `urgency`, and `assignment_group`; read the created record |
   | Native SRE Agent incident platform | Read assigned incidents; update acknowledgement/state fields, `work_notes`, `close_code`, and `close_notes`; read referenced assignment group and user records |

5. Test table, field, and reference ACLs while impersonating the integration
   user. A table grant alone is insufficient when field ACLs or business rules
   reject a write.

If the native SRE Agent connector is configured with a different identity,
apply the same least-privilege principle to that identity. Do not share a human
administrator account between the simulator and the native connector.

## 3. Configure OAuth client credentials for the simulator

The simulator uses the OAuth 2.0 client-credentials grant. It does not require a
username or password.

1. Verify the system property
   `glide.oauth.inbound.client.credential.grant_type.enabled` is `true`. Create
   it as a Boolean property if the instance does not expose it. Restart the
   instance if ServiceNow requires a restart for the property to take effect.
2. Create an OAuth application for inbound client credentials.
3. Create an OAuth Application User mapping from that application to the
   least-privilege integration user.
4. Copy the generated client ID and client secret to a secure local secret
   store. The secret is shown only for configuration and must not be committed.
5. Restrict the OAuth application to the incident API scope when the installed
   ServiceNow release exposes REST OAuth scope controls. ACLs remain the
   enforcement boundary, so keep the application user restricted even when a
   narrower scope is configured.

Copy `.env.example` to an ignored `.env` or export the variables from your
secret manager:

```bash
SERVICENOW_INSTANCE_URL=https://dev442167.service-now.com
SERVICENOW_CLIENT_ID=<client-id>
SERVICENOW_CLIENT_SECRET=<client-secret>
SERVICENOW_ASSIGNMENT_GROUP_SYS_ID=<zava-power-sre-group-sys-id>
# Optional when the default /oauth_token.do endpoint is not used:
SERVICENOW_TOKEN_URL=https://dev442167.service-now.com/oauth_token.do
# Optional only when the OAuth application requires a scope:
SERVICENOW_SCOPE=<restricted-scope>
```

Do not add an integration username: the OAuth Application User mapping selects
the ServiceNow identity for a client-credentials token.

## 4. Configure native ServiceNow incident ingestion

In [Azure SRE Agent](https://sre.azure.com):

1. Open the Zava Power agent and add **ServiceNow** as an incident platform.
2. Enter `https://dev442167.service-now.com`.
3. Use the authentication method presented by the SRE Agent tenant. The native
   connector can expose an interactive OAuth authorization flow; the
   simulator's client credentials are a separate integration and must not be
   pasted into fields that expect interactive OAuth.
4. Scope ingestion to incidents assigned to `Zava Power SRE`.
5. Save the connection and verify an assigned test incident appears with both:
   - its human-readable number, such as `INC0012345`; and
   - its ServiceNow `sys_id`.

Native actions use the **`sys_id`**. The incident number is display data and
must not be passed to `GetServiceNowIncident`,
`AcknowledgeServiceNowIncident`, `PostServiceNowDiscussionEntry`, or
`ResolveServiceNowIncident`.

## 5. Configure the response plan

Create or update the response plan in **Incidents > Response plans**:

- **Name:** `auto-investigate`
- **Incident source/platform:** ServiceNow
- **Assignment scope:** `Zava Power SRE`
- **Handling agent:** `incident-handler`
- **Instructions:** use the triggering ServiceNow `sys_id`; acknowledge the
  same incident; investigate with Azure telemetry; post meaningful work notes;
  remediate only within policy; validate recovery; resolve the same incident.

Do not attach this plan to Azure Monitor incident ingestion and do not apply the
deleted custom create, lookup, work-note, or resolve tools. The native
ServiceNow tools own the lifecycle.

## 6. Reapply and validate

After changing OAuth properties, ACLs, roles, assignment records, or connector
credentials:

1. Restart the PDI when required by ServiceNow.
2. Reconnect or reauthorize the native incident platform in SRE Agent.
3. Re-save the response plan and reapply the repository agents/skills with
   `scripts/configure-agent.sh`.
4. Create a disposable test incident assigned to `Zava Power SRE`. Either use
   the ServiceNow UI or run `python simulator/demo.py` and explicitly type
   `CREATE` for a ServiceNow-backed scenario.
5. Confirm the native platform ingests the incident, the response plan passes
   its `sys_id`, work notes appear on that same record, and resolution updates
   that same record.

The native poller may take approximately one minute. If no incident appears,
check instance availability, assignment-group filtering, OAuth authorization,
ACL denials, and response-plan source selection before changing agent logic.

## Failure guide

| Failure | Action |
|---------|--------|
| Missing environment variable | Populate the ignored `.env` or secret-store injection; do not add a fallback secret |
| Token request rejected | Verify client credentials, inbound grant property, application-user mapping, and scope |
| HTTP 401/403 from Table API | Inspect the integration user's roles plus table, field, and reference ACLs |
| Timeout/connection failure | Wake the PDI, verify DNS/TLS/proxy access, then retry |
| Incident is created but not ingested | Verify assignment-group `sys_id`, native platform filter, connection health, and response-plan applicability |
| Native action cannot find `INC...` | Pass the triggering `sys_id`, not the display number |
