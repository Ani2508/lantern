param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("on", "off")]
    [string]$Action
)

$FunctionName = if ($env:FN_API) { $env:FN_API } else { "lantern-dev-api" }
$Region = if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-1" }

if ($Action -eq "off") {
    Write-Host "Setting reserved concurrency of $FunctionName to 0 (kill switch)"
    aws lambda put-function-concurrency --function-name $FunctionName --reserved-concurrent-executions 0 --region $Region
} else {
    Write-Host "Clearing reserved concurrency of $FunctionName (API on)"
    aws lambda delete-function-concurrency --function-name $FunctionName --region $Region
}
