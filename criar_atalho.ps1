# Cria um atalho na Area de Trabalho do Windows para abrir o Sistema de
# Afastamentos SCDP com um duplo clique, sem precisar abrir VSCode,
# terminal ou qualquer outro programa.
#
# Como usar: clique com o botao direito neste arquivo e escolha
# "Executar com o PowerShell". Se aparecer um aviso de seguranca, veja o
# Guia de instalacao (passo do atalho) para saber como liberar.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Alvo = Join-Path $ScriptDir "iniciar_sistema.bat"

if (-not (Test-Path $Alvo)) {
    Write-Host "Nao encontrei o arquivo iniciar_sistema.bat nesta pasta." -ForegroundColor Red
    Write-Host "Confirme que este script esta na mesma pasta do sistema (scdp_afastamentos)." -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit 1
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$CaminhoAtalho = Join-Path $Desktop "Sistema SCDP - Afastamentos.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Atalho = $WshShell.CreateShortcut($CaminhoAtalho)
$Atalho.TargetPath = $Alvo
$Atalho.WorkingDirectory = $ScriptDir
$Atalho.IconLocation = "$env:SystemRoot\System32\SHELL32.dll,13"
$Atalho.Description = "Abre o sistema de solicitacao de afastamentos (SCDP) no navegador"
$Atalho.Save()

Write-Host ""
Write-Host "Pronto! Foi criado o atalho 'Sistema SCDP - Afastamentos' na sua Area de Trabalho." -ForegroundColor Green
Write-Host "A partir de agora, so precisa dar dois cliques nele para abrir o sistema." -ForegroundColor Green
Write-Host ""
Read-Host "Pressione Enter para fechar"
