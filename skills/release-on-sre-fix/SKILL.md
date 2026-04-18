---
metadata:
  api_version: azuresre.ai/v2
  kind: Skill
name: release-on-sre-fix
description: |
  Authoritative skill for the release-orchestrator agent. When a
  PowerGrid-Build succeeds, this skill decides whether to trigger
  PowerGrid-Release. It triggers ONLY for SRE-Agent-authored fixes
  (identified via ADO build tag 'sre-agent-fix' or service-principal
  requestedFor). Human developer commits flow through normal CI/CD
  gates and are NOT auto-released by this agent.
---

# Release on SRE Fix

## When to use
Triggered by `BuildSucceeded` events on `PowerGrid-Build` (pipeline
ID 4). The release-orchestrator agent loads this skill on every such
event.

## Why a filter is necessary
ADO release triggers do not natively filter by author or commit tag.
Without this skill, every successful build (including human dev
commits) would auto-release. We want auto-release ONLY for SRE-Agent
fixes that have already been validated by the agent's own diagnosis.

## Decision flow

### 1. Check the build's source
Call:

```
CheckBuildSourceTag(build_id)
```

Returns `is_sre_agent_fix: true|false` based on:
- ADO build tag `sre-agent-fix` present, OR
- `requestedFor.uniqueName` matches the SRE Agent service principal
  UPN (configured in the tool YAML).

### 2. Decision matrix

| `is_sre_agent_fix` | Action |
|---|---|
| `true`  | Trigger release (proceed to step 3) |
| `false` | NO ACTION. Post a Teams note: "Build #N succeeded — human-author build, leaving release to normal CI/CD." Then exit. |

### 3. Trigger PowerGrid-Release for the SRE-Agent build
Call:

```
TriggerAdoRelease(release_pipeline_id="5",
                  build_id=<the BuildSucceeded build_id>,
                  reason="auto-release of SRE-Agent fix for buildId=<id>")
```

This sets a `sre-agent-release-<release_id>` audit tag on the source
build so the chain (incident → fix PR → build → release) is traceable.

### 4. Post to Teams
"🤖 Auto-release triggered: PowerGrid-Release run #<release_id>
materializing SRE-Agent fix from build #<build_id>. The
deployment-validator agent will validate post-deploy."

Done. The deployment-validator agent will pick up the resulting
ReleaseSucceeded event using the `deployment-validation` skill.

## Loop-safety notes
- Never trigger a release for a build that wasn't tagged — even if
  the build originated from an SRE-Agent-authored commit, untagged
  builds suggest something is off; let humans investigate.
- Never trigger a release if the build's `result != succeeded` (the
  CheckBuildSourceTag tool returns this; if not "succeeded", abort).
- Do not chain triggers: this agent does not trigger another build
  from a release (the deployment-validator handles rollback +
  fix-PR + new build chain on regression).
