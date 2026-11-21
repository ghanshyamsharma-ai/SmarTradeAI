param(
    [string] $Region = "ap-south-1",
    [string] $AccountId = "ACCOUNT_ID",
    [string] $RepositoryName = "smartraderai",
    [string] $Cluster = "smartraderai-cluster",
    [string] $Service = "smartraderai-core",
    [string] $Family = "smartraderai",
    [string] $JwtSecretArn = "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:smartraderai/jwt-secret"
)

$ErrorActionPreference = "Stop"
$registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$image = "$registry/$RepositoryName`:latest"
$template = Join-Path $PSScriptRoot "ecs-task-definition.json"

Write-Host "Building and pushing $image"
aws ecr get-login-password --region $Region |
    docker login --username AWS --password-stdin $registry
docker build -t $image .
docker push $image

Write-Host "Registering ECS task definition"
$task = Get-Content -Path $template -Raw | ConvertFrom-Json
$task.containerDefinitions[0].image = $image
$secret = $task.containerDefinitions[0].secrets | Where-Object { $_.name -eq "JWT_SECRET" }
if ($secret) { $secret.valueFrom = $JwtSecretArn }

$tempTask = Join-Path $env:TEMP "smartraderai-taskdef.json"
$task | ConvertTo-Json -Depth 40 | Set-Content -Path $tempTask -Encoding UTF8
aws ecs register-task-definition --region $Region --cli-input-json "file://$tempTask"

Write-Host "Updating ECS service"
aws ecs update-service --region $Region --cluster $Cluster --service $Service --task-definition $Family
