# Rode este script no PowerShell COMO ADMINISTRADOR.
# Ele remove as tarefas antigas (criadas via schtasks, com o bug de duração
# desativada) e recria com repeticao indefinida de verdade.

$ErrorActionPreference = "Stop"

# --- Checagem: precisa ser admin, senão Register-ScheduledTask falha calado ---
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERRO: este script precisa rodar em um PowerShell aberto como Administrador." -ForegroundColor Red
    Write-Host "Feche esta janela, abra o PowerShell com botao direito > 'Executar como administrador', e rode de novo." -ForegroundColor Red
    exit 1
}

# ============================================================
# AJUSTE ESTE CAMINHO para a pasta real do seu projeto
# ============================================================
$ProjectPath = "C:\Users\Valte\Documents\TCC\Estacao Meteorologica Portatil\weather-station"

if (-not (Test-Path "$ProjectPath\run_ingest.bat")) {
    Write-Host "ERRO: nao encontrei $ProjectPath\run_ingest.bat -- confira o caminho em `$ProjectPath." -ForegroundColor Red
    exit 1
}

# --- Remove tarefas antigas, se existirem ---
Unregister-ScheduledTask -TaskName "TCC_Ingest_Clima" -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "TCC_Previsao_Clima" -Confirm:$false -ErrorAction SilentlyContinue

# --- Configurações comuns ---
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

try {
    # --- Tarefa de ingestão (roda no minuto 00 de cada hora, para sempre) ---
    $actionIngest = New-ScheduledTaskAction -Execute "$ProjectPath\run_ingest.bat"
    $triggerIngest = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
        -RepetitionInterval (New-TimeSpan -Hours 1)
    # Duration = "" é o valor que o Agendador de Tarefas interpreta como
    # "repetir indefinidamente". Não existe parâmetro direto pra isso no
    # New-ScheduledTaskTrigger, então ajustamos a propriedade manualmente.
    $triggerIngest.Repetition.Duration = ""

    Register-ScheduledTask -TaskName "TCC_Ingest_Clima" `
        -Action $actionIngest -Trigger $triggerIngest -Settings $settings `
        -Description "Ingestao de dados externos (Open-Meteo) a cada hora" `
        -RunLevel Highest -ErrorAction Stop | Out-Null

    Write-Host "Tarefa TCC_Ingest_Clima criada com sucesso." -ForegroundColor Green
}
catch {
    Write-Host "ERRO ao criar TCC_Ingest_Clima:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

try {
    # --- Tarefa de previsão (roda 5 min depois, para dar tempo da ingestão terminar) ---
    $actionPredict = New-ScheduledTaskAction -Execute "$ProjectPath\run_predict.bat"
    $triggerPredict = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) `
        -RepetitionInterval (New-TimeSpan -Hours 1)
    $triggerPredict.Repetition.Duration = ""

    Register-ScheduledTask -TaskName "TCC_Previsao_Clima" `
        -Action $actionPredict -Trigger $triggerPredict -Settings $settings `
        -Description "Gera previsoes com o modelo treinado a cada hora" `
        -RunLevel Highest -ErrorAction Stop | Out-Null

    Write-Host "Tarefa TCC_Previsao_Clima criada com sucesso." -ForegroundColor Green
}
catch {
    Write-Host "ERRO ao criar TCC_Previsao_Clima:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

Write-Host "`nVerificando tarefas criadas..."
Get-ScheduledTask -TaskName "TCC_Ingest_Clima", "TCC_Previsao_Clima" | Format-Table TaskName, State
Get-ScheduledTaskInfo -TaskName "TCC_Ingest_Clima" | Format-List NextRunTime, LastRunTime, LastTaskResult
Get-ScheduledTaskInfo -TaskName "TCC_Previsao_Clima" | Format-List NextRunTime, LastRunTime, LastTaskResult