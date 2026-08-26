# Scenario 1 — Service Outage Prompts

## Initial Investigation
```
The PowerGrid outage-api is returning 503 errors. Can you investigate 
what's causing the service to fail and find the root cause?
```

## After RCA
```
Can you fix the outage-api service? The runbook in the knowledge base 
has the remediation steps.
```

## Validation
```
Can you verify that the outage-api is now healthy and responding 
with 200 status codes?
```

## ServiceNow lifecycle
```
Use the triggering ServiceNow incident's sys_id. Confirm the native response
plan acknowledged that incident, posted the root-cause analysis and remediation
as discussion entries, and resolved the same incident after validation. Do not
create or look up a second incident.
```
