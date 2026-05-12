$paths = @('app\core\*.py', 'app\skills\*.py', 'app\services\*.py', 'app\personas\*.md', 'app\main.py', 'requirements.txt', 'Dockerfile', '.env.example')
$output = "OROVA_AUDIT_PACKAGE.md"
"#" + " OROVA Nova Mission Control Audit Package" | Out-File -FilePath $output -Encoding utf8
"" | Out-File -FilePath $output -Append -Encoding utf8

foreach ($p in $paths) {
    Get-ChildItem -Path $p -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "Adding: $($_.FullName)"
        "## File: $($_.FullName)" | Out-File -FilePath $output -Append -Encoding utf8
        '```' | Out-File -FilePath $output -Append -Encoding utf8
        Get-Content $_.FullName | Out-File -FilePath $output -Append -Encoding utf8
        '```' | Out-File -FilePath $output -Append -Encoding utf8
        "" | Out-File -FilePath $output -Append -Encoding utf8
    }
}
Write-Host "✅ Audit Package Created: OROVA_AUDIT_PACKAGE.md"
