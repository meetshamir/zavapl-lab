// ── Azure Monitor Alert Rules for PowerGrid Services ──

param location string
param workloadName string
param tags object
param logAnalyticsWorkspaceId string
param appInsightsId string

// ── Action Group (email + webhook placeholder) ──
resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${workloadName}-sre'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'SREAlert'
    enabled: true
  }
}

// ── Alert: HTTP 5xx errors ──
resource http5xxAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'alert-${workloadName}-http-5xx'
  location: location
  tags: tags
  properties: {
    displayName: 'PowerGrid — HTTP 5xx Errors Detected'
    description: 'Fires when any PowerGrid service returns 5xx errors'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    scopes: [appInsightsId]
    criteria: {
      allOf: [
        {
          query: 'requests | where resultCode startswith "5" | summarize count() by bin(timestamp, 1m)'
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 5
          failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

// ── Alert: High response time ──
resource latencyAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'alert-${workloadName}-high-latency'
  location: location
  tags: tags
  properties: {
    displayName: 'PowerGrid — High Response Time Detected'
    description: 'Fires when avg response time exceeds 3 seconds'
    severity: 3
    enabled: true
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    scopes: [appInsightsId]
    criteria: {
      allOf: [
        {
          query: 'requests | summarize avg(duration) by bin(timestamp, 1m) | where avg_duration > 3000'
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

// ── Alert: Container restart ──
resource restartAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'alert-${workloadName}-container-restart'
  location: location
  tags: tags
  properties: {
    displayName: 'PowerGrid — Container Restarts Detected'
    description: 'Fires when container apps restart repeatedly'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    scopes: [logAnalyticsWorkspaceId]
    criteria: {
      allOf: [
        {
          query: 'ContainerAppSystemLogs_CL | where Reason_s == "BackOff" or Reason_s == "CrashLoopBackOff" | summarize count() by bin(TimeGenerated, 1m)'
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 3
          failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

output actionGroupId string = actionGroup.id
