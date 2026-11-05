# Builds the Revit add-in and installs it for the current user.
# Usage (PowerShell, from the revit-mcp folder):
#   .\install.ps1 -RevitVersion 2025
param(
    [ValidateSet("2024", "2025", "2026")]
    [string]$RevitVersion = "2025"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Building add-in for Revit $RevitVersion..."
dotnet build "$root\addin\RevitMcp.csproj" -c Release -p:RevitVersion=$RevitVersion
if ($LASTEXITCODE -ne 0) { throw "Build failed" }

$build   = "$root\addin\bin\Release\$RevitVersion"
$addins  = "$env:APPDATA\Autodesk\Revit\Addins\$RevitVersion"
$target  = "$addins\RevitMcp"
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item "$build\*" $target -Recurse -Force

$manifest = (Get-Content "$root\addin\RevitMcp.addin" -Raw) -replace '<Assembly>.*</Assembly>', "<Assembly>$target\RevitMcp.dll</Assembly>"
Set-Content -Path "$addins\RevitMcp.addin" -Value $manifest -Encoding UTF8

Write-Host "Installing Python MCP server dependencies..."
python -m pip install -r "$root\server\requirements.txt"

Write-Host ""
Write-Host "Done. Restart Revit and click 'Always Load' when asked about 'Revit MCP Bridge'."
Write-Host "Then add this to Claude Desktop config (%APPDATA%\Claude\claude_desktop_config.json):"
$py = (Get-Command python).Source -replace '\\', '\\'
$srv = "$root\server\revit_mcp_server.py" -replace '\\', '\\'
Write-Host @"
{
  "mcpServers": {
    "revit": { "command": "$py", "args": ["$srv"] }
  }
}
"@
