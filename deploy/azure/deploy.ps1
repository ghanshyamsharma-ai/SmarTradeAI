param(
    [string] $ResourceGroup = "smartraderai-rg",
    [string] $Location = "centralindia",
    [string] $AppName = "smartraderai",
    [string] $AcrName = "smartraderaiacr",
    [string] $JwtSecret = $env:JWT_SECRET,
    [string] $RedisUrl = "",
    [string] $DatabaseUrl = "",
    [string] $EventBus = "memory"
)

$ErrorActionPreference = "Stop"
if (-not $JwtSecret) {
    throw "Set -JwtSecret or the JWT_SECRET environment variable before deploying."
}

$image = "$AcrName.azurecr.io/smartraderai:latest"
$template = Join-Path $PSScriptRoot "main.bicep"

Write-Host "Preparing Azure Container Registry"
az group create --name $ResourceGroup --location $Location
az acr create --resource-group $ResourceGroup --name $AcrName --sku Basic --admin-enabled false
$acrId = az acr show --resource-group $ResourceGroup --name $AcrName --query id -o tsv
az acr login --name $AcrName

Write-Host "Building and pushing $image"
docker build -t $image .
docker push $image

Write-Host "Deploying Container App"
az deployment group create `
    --resource-group $ResourceGroup `
    --template-file $template `
    --parameters appName=$AppName `
                 containerImage=$image `
                 "jwtSecret=$JwtSecret" `
                 "redisUrl=$RedisUrl" `
                 "databaseUrl=$DatabaseUrl" `
                 eventBus=$EventBus `
                 acrResourceId=$acrId
