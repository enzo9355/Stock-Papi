[CmdletBinding()]
param(
    [string]$DataRoot = 'D:\StockPapiData',
    [string]$Bucket = 'line-stock-bot-498908-quant-snapshots'
)

$ErrorActionPreference = 'Stop'
if ($DataRoot -ne 'D:\StockPapiData') { throw 'Data root is not allowlisted' }
if ($Bucket -ne 'line-stock-bot-498908-quant-snapshots') { throw 'Bucket is not allowlisted' }

$PublishRoot = Join-Path $DataRoot 'publish\quant\v1'
$ResolvedRoot = (Resolve-Path -LiteralPath $PublishRoot).Path
if (((Get-Item -LiteralPath $ResolvedRoot).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'Publish root must not be a reparse point'
}
$Gcloud = (Get-Command gcloud -ErrorAction Stop).Source

function Assert-AllowlistedPath {
    param([string]$Path)
    $Resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not $Resolved.StartsWith($ResolvedRoot + [IO.Path]::DirectorySeparatorChar)) {
        throw 'Upload path escaped publish root'
    }
    $Current = Get-Item -LiteralPath $Resolved
    while ($Current.FullName -ne $ResolvedRoot) {
        if (($Current.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Upload path contains a reparse point'
        }
        $Current = $Current.Parent
    }
    return $Resolved
}

function Invoke-GcloudCopy {
    param(
        [string]$Source,
        [string]$Destination,
        [switch]$NoClobber
    )
    $Arguments = @('storage', 'cp', '--quiet')
    if ($NoClobber) { $Arguments += '--no-clobber' }
    $Arguments += @($Source, $Destination)
    & $Gcloud @Arguments
    if ($LASTEXITCODE -ne 0) { throw "gcloud upload failed with exit code $LASTEXITCODE" }
}

$UploadedMarkets = @()
foreach ($Market in @('TW', 'US')) {
    $LatestPath = Join-Path $ResolvedRoot "latest-$Market.json"
    if (-not (Test-Path -LiteralPath $LatestPath -PathType Leaf)) { continue }
    $LatestPath = Assert-AllowlistedPath $LatestPath
    $Latest = Get-Content -LiteralPath $LatestPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($Latest.schema_version -ne 2 -or $Latest.market -ne $Market) {
        throw "Invalid latest pointer for $Market"
    }
    $ManifestRelative = [string]$Latest.manifest
    if ($ManifestRelative -notmatch '^manifests/[A-Z]+-[0-9TZ]+-[0-9a-f]{12}\.json$') {
        throw "Invalid manifest path for $Market"
    }
    $ManifestPath = Assert-AllowlistedPath (Join-Path $ResolvedRoot $ManifestRelative)
    if ((Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Latest.manifest_sha256) {
        throw "Manifest hash mismatch for $Market"
    }
    $Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($Manifest.schema_version -ne 2 -or $Manifest.market -ne $Market) {
        throw "Invalid manifest for $Market"
    }

    # Upload objects
    foreach ($Property in $Manifest.symbols.PSObject.Properties) {
        $Entry = $Property.Value
        $ObjectRelative = [string]$Entry.path
        if ($ObjectRelative -notmatch '^objects/[0-9a-f]{64}\.json\.gz$') {
            throw "Invalid object path for $Market"
        }
        $ObjectPath = Assert-AllowlistedPath (Join-Path $ResolvedRoot $ObjectRelative)
        $Object = Get-Item -LiteralPath $ObjectPath
        if ($Object.Length -ne [long]$Entry.size) { throw "Object size mismatch for $Market" }
        if ((Get-FileHash -LiteralPath $ObjectPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.sha256) {
            throw "Object hash mismatch for $Market"
        }
        Invoke-GcloudCopy $ObjectPath "gs://$Bucket/quant/v1/$ObjectRelative" -NoClobber
    }

    # Upload manifest
    Invoke-GcloudCopy $ManifestPath "gs://$Bucket/quant/v1/$ManifestRelative" -NoClobber

    # Upload latest pointer
    Invoke-GcloudCopy $LatestPath "gs://$Bucket/quant/v1/latest-$Market.json"
    $UploadedMarkets += $Market
}

$Status = @{
    uploaded_at = [DateTimeOffset]::Now.ToString('o')
    markets = $UploadedMarkets
    bucket = $Bucket
} | ConvertTo-Json -Compress
Set-Content -LiteralPath (Join-Path $DataRoot 'logs\upload-status.json') -Value $Status -Encoding utf8
Write-Output "Uploaded quant snapshots: $($UploadedMarkets -join ',')"
