# run.ps1 — DX helper para o Go2 Voice Control (servidor) — versão Windows
#
# Uso:
#   .\run.ps1 voz                 -> docker compose --profile voz up
#   .\run.ps1 inference-debug     -> docker compose --profile inference-debug up
#   .\run.ps1 keyboard-control    -> docker compose run --rm teclado
#   .\run.ps1 build               -> docker compose build
#   .\run.ps1 logs [servico]      -> docker compose logs -f [servico opcional]
#   .\run.ps1 down                -> docker compose down
#   .\run.ps1 gpu-check           -> checa se ha GPU NVIDIA disponivel pro Docker
#   .\run.ps1                     -> mostra esta ajuda

param(
    [Parameter(Position = 0)]
    [string]$Command = "help",

    [Parameter(Position = 1)]
    [string]$Service = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

function Print-Banner {
    Write-Host ""
    Write-Host "  ██████╗  ██████╗ ██████╗ "
    Write-Host " ██╔════╝ ██╔═══██╗╚════██╗"
    Write-Host " ██║  ███╗██║   ██║ █████╔╝"
    Write-Host " ██║   ██║██║   ██║██╔═══╝ "
    Write-Host " ╚██████╔╝╚██████╔╝███████╗"
    Write-Host "  ╚═════╝  ╚═════╝ ╚══════╝"
    Write-Host "        VOICE CONTROL — SERVIDOR (Windows)"
    Write-Host ""
}

function Check-Gpu {
    Write-Host "==> Checando disponibilidade de GPU NVIDIA..."
    $gpuInfo = docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi --query-gpu=name --format=csv,noheader 2>$null

    if ($LASTEXITCODE -eq 0 -and $gpuInfo) {
        Write-Host "    GPU detectada: $gpuInfo"
        Write-Host "    O container 'inference' deve usar CUDA automaticamente."
    } else {
        Write-Host "    Nenhuma GPU NVIDIA acessivel pelo Docker."
        Write-Host "    O container 'inference' vai rodar em CPU (fallback automatico, sem erro)."
    }
    Write-Host ""
}

function Print-Help {
    Print-Banner
    Write-Host "  USO"
    Write-Host "  ───────────────────────────────────────────────────────────────────"
    Write-Host "    .\run.ps1 <comando> [argumentos]"
    Write-Host ""
    Write-Host "  COMANDOS DISPONIVEIS"
    Write-Host "  ───────────────────────────────────────────────────────────────────"
    Write-Host ""
    Write-Host "    ┌─ PRODUCAO ─────────────────────────────────────────────────────"
    Write-Host "    │"
    Write-Host "    │  voz                  Sobe o pipeline completo:"
    Write-Host "    │                       redis + inference + robot-control"
    Write-Host "    │                       (checa GPU antes de subir)"
    Write-Host "    │"
    Write-Host "    └────────────────────────────────────────────────────────────────"
    Write-Host ""
    Write-Host "    ┌─ DEBUG ────────────────────────────────────────────────────────"
    Write-Host "    │"
    Write-Host "    │  inference-debug      Sobe so redis + inference."
    Write-Host "    │                       Testa wake word / Whisper / classificador"
    Write-Host "    │                       sem precisar do robo conectado."
    Write-Host "    │                       (checa GPU antes de subir)"
    Write-Host "    │"
    Write-Host "    │  keyboard-control     Controle manual do robo por teclado,"
    Write-Host "    │                       sem pipeline de voz (docker compose run)."
    Write-Host "    │"
    Write-Host "    └────────────────────────────────────────────────────────────────"
    Write-Host ""
    Write-Host "    ┌─ UTILITARIOS ──────────────────────────────────────────────────"
    Write-Host "    │"
    Write-Host "    │  build                Builda todas as imagens (docker compose build)"
    Write-Host "    │  logs [servico]       Segue os logs (todos, ou de um servico)"
    Write-Host "    │  down                 Para e remove os containers"
    Write-Host "    │  ps                   Lista containers do projeto em execucao"
    Write-Host "    │  gpu-check            Checa se ha GPU NVIDIA disponivel pro Docker"
    Write-Host "    │  help                 Mostra esta ajuda"
    Write-Host "    │"
    Write-Host "    └────────────────────────────────────────────────────────────────"
    Write-Host ""
    Write-Host "  EXEMPLOS"
    Write-Host "  ───────────────────────────────────────────────────────────────────"
    Write-Host "    .\run.ps1 voz"
    Write-Host "    .\run.ps1 inference-debug"
    Write-Host "    .\run.ps1 keyboard-control"
    Write-Host "    .\run.ps1 logs inference"
    Write-Host "    .\run.ps1 gpu-check"
    Write-Host "    .\run.ps1 down"
    Write-Host ""
    Write-Host "  Documentacao completa: .\README.md"
    Write-Host "  Registro de bugs/solucoes: .\docs\PROBLEMAS_E_SOLUCOES.md"
    Write-Host ""
}

switch ($Command) {
    "voz" {
        Check-Gpu
        Write-Host "==> Subindo pipeline completo (profile: voz)..."
        docker compose --profile voz up
    }

    "inference-debug" {
        Check-Gpu
        Write-Host "==> Subindo modo debug (redis + inference, sem robo)..."
        docker compose --profile inference-debug up
    }

    "keyboard-control" {
        Write-Host "==> Iniciando controle manual por teclado..."
        docker compose run --rm teclado
    }

    "build" {
        Write-Host "==> Buildando todas as imagens..."
        docker compose build
    }

    "logs" {
        if ($Service -ne "") {
            Write-Host "==> Seguindo logs de: $Service"
            docker compose logs -f $Service
        } else {
            Write-Host "==> Seguindo logs de todos os servicos..."
            docker compose logs -f
        }
    }

    "down" {
        Write-Host "==> Parando e removendo containers..."
        docker compose down
    }

    "ps" {
        docker compose ps
    }

    "gpu-check" {
        Check-Gpu
    }

    { $_ -in "help", "-h", "--help" } {
        Print-Help
    }

    default {
        Write-Host "Comando desconhecido: '$Command'"
        Write-Host ""
        Print-Help
        exit 1
    }
}