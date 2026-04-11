// ── SRE Agent with User-Assigned Managed Identity ──

param location string
param workloadName string
param tags object
param targetResourceGroupName string

// ── Managed Identity for SRE Agent ──
resource sreIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${workloadName}-sre'
  location: location
  tags: tags
}

// ── RBAC: Reader on target resource group ──
resource readerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sreIdentity.id, targetResourceGroupName, 'Reader')
  properties: {
    principalId: sreIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
  }
}

// ── RBAC: Monitoring Reader ──
resource monitoringReaderRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sreIdentity.id, targetResourceGroupName, 'Monitoring Reader')
  properties: {
    principalId: sreIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '43d0d8ad-25c7-4714-9337-8ba259a9fe05')
  }
}

// ── RBAC: Log Analytics Reader ──
resource logAnalyticsReaderRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sreIdentity.id, targetResourceGroupName, 'Log Analytics Reader')
  properties: {
    principalId: sreIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '73c42c96-874c-492b-b04d-ab87d138a893')
  }
}

// ── RBAC: Container App Contributor (for remediation) ──
resource containerAppContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sreIdentity.id, targetResourceGroupName, 'Container App Contributor')
  properties: {
    principalId: sreIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b2e6d14c-4a46-4520-8e5a-287fbb6eb49c')
  }
}

output agentName string = 'sre-${workloadName}'
output agentIdentityId string = sreIdentity.id
output agentIdentityPrincipalId string = sreIdentity.properties.principalId
