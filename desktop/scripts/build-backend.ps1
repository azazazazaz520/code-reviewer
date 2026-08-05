$ErrorActionPreference = "Stop"

$desktopRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = (Resolve-Path (Join-Path $desktopRoot "..\backend")).Path
$pyInstaller = Join-Path $backendRoot ".venv\Scripts\pyinstaller.exe"
$backendOutput = Join-Path $backendRoot "dist\code-reviewer-backend"
$resourceRoot = Join-Path $desktopRoot "resources\backend"

if (-not (Test-Path -LiteralPath $pyInstaller)) {
    throw "未找到 PyInstaller，请先在 backend 执行 uv sync --extra desktop"
}

Push-Location $backendRoot
try {
    & $pyInstaller --clean --noconfirm desktop.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 构建失败，退出码: $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $backendOutput)) {
    throw "PyInstaller 未生成预期目录: $backendOutput"
}

if ([IO.Path]::GetFullPath($resourceRoot) -ne [IO.Path]::GetFullPath((Join-Path $desktopRoot "resources\backend"))) {
    throw "拒绝清理非预期 sidecar 资源目录: $resourceRoot"
}
if (Test-Path -LiteralPath $resourceRoot) {
    Remove-Item -LiteralPath $resourceRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $resourceRoot | Out-Null
Copy-Item -Path (Join-Path $backendOutput "*") -Destination $resourceRoot -Recurse -Force
Write-Output "sidecar resources copied to $resourceRoot"
