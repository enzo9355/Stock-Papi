function Protect-NativeProcessText {
    param([AllowEmptyString()][string]$Text)

    $Safe = $Text -replace (
        '(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+'
    ), 'Bearer [REDACTED]'
    return $Safe -replace (
        '(?i)\b(token|password|authorization|cookie|secret)' +
        '\s*[:=]\s*[^\s;]+'
    ), '$1=[REDACTED]'
}

function Invoke-NativeProcessCaptured {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$Arguments = @(),
        [switch]$AllowFailure
    )

    $PreviousErrorActionPreference = $ErrorActionPreference
    $ExitCode = 1
    try {
        $ErrorActionPreference = 'Continue'
        $Output = & $FilePath @Arguments 2>&1
        $ExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
    $Text = Protect-NativeProcessText ($Output | Out-String)
    if ($ExitCode -ne 0 -and -not $AllowFailure) {
        throw "Native process failed with exit code ${ExitCode}: $Text"
    }
    return [pscustomobject]@{
        exit_code = $ExitCode
        text = $Text
    }
}
