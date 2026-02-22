# Script de Automação para Criação do Executável e Instalador (Windows)

Write-Host "🚀 Iniciando processo de compilação..." -ForegroundColor Cyan

# 1. Limpeza de builds anteriores
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

# 2. Compilação com PyInstaller
Write-Host "📦 Gerando executável com PyInstaller..." -ForegroundColor Yellow
pyinstaller --clean AtendimentoBot.spec

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erro na compilação do PyInstaller!" -ForegroundColor Red
    exit $LASTEXITCODE
}

# 3. Criação do Instalador com Inno Setup
$ISCC = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $ISCC)) {
    $ISCC = "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
}

if (Test-Path $ISCC) {
    Write-Host "🔨 Gerando instalador (Setup) com Inno Setup..." -ForegroundColor Yellow
    & $ISCC installer_script.iss
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Instalador criado com sucesso em: .\installer\Setup_AtendimentoBot.exe" -ForegroundColor Green
    }
    else {
        Write-Host "⚠️ Falha ao gerar o instalador Inno Setup." -ForegroundColor Yellow
    }
}
else {
    Write-Host "ℹ️ Inno Setup não encontrado. O executável standalone está disponível na pasta .\dist\AtendimentoBot" -ForegroundColor Gray
}

Write-Host "🏁 Processo concluído!" -ForegroundColor Cyan
