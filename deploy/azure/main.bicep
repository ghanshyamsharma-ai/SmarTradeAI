@description('Azure region for the SmartTrade AI Pro resources')
param location string = resourceGroup().location

@description('Container Apps environment and application name')
param appName string = 'smarttrade-ai-pro'

@description('Fully qualified container image, for example myacr.azurecr.io/smarttrade-ai-pro:latest')
param containerImage string

@secure()
@description('JWT signing secret')
param jwtSecret string

@description('Optional Redis connection string')
param redisUrl string = ''

@description('Optional SQLAlchemy connection string')
param databaseUrl string = ''

@description('Optional event bus backend: memory, redis or kafka')
param eventBus string = 'memory'

@description('Existing Azure Container Registry resource ID, if the image is private')
param acrResourceId string = ''

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${appName}-env'
  location: location
  properties: {}
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: true
      }
      secrets: [
        {
          name: 'jwt-secret'
          value: jwtSecret
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'core'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'PYTHONUNBUFFERED', value: '1' }
            { name: 'JWT_SECRET', secretRef: 'jwt-secret' }
            { name: 'MARKET_REFRESH_SECONDS', value: '15' }
            { name: 'EVENT_BUS', value: eventBus }
            { name: 'REDIS_URL', value: redisUrl }
            { name: 'DATABASE_URL', value: databaseUrl }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = if (!empty(acrResourceId)) {
  name: last(split(acrResourceId, '/'))
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(acrResourceId)) {
  scope: acr
  name: guid(app.id, acrResourceId, 'AcrPull')
  properties: {
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

output fqdn string = app.properties.configuration.ingress.fqdn
output appName string = app.name
