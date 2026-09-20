#!/usr/bin/env bash
# run.sh — DX helper para o Go2 Voice Control (servidor)
#
# Uso:
#   ./run.sh up                  -> docker compose up
#   ./run.sh build               -> docker compose build
#   ./run.sh logs [servico]      -> docker compose logs -f [servico opcional]
#   ./run.sh down                -> docker compose down
#   ./run.sh gpu-check           -> checa se há GPU NVIDIA disponível pro Docker
#   ./run.sh                     -> mostra esta ajuda

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

CMD="${1:-help}"

print_banner() {
cat <<'EOF'

  ██████╗  ██████╗ ██████╗
 ██╔════╝ ██╔═══██╗╚════██╗
 ██║  ███╗██║   ██║ █████╔╝
 ██║   ██║██║   ██║██╔═══╝
 ╚██████╔╝╚██████╔╝███████╗
  ╚═════╝  ╚═════╝ ╚══════╝
        VOICE CONTROL — SERVIDOR

EOF
}

check_gpu() {
    echo "==> Checando disponibilidade de GPU NVIDIA..."
    local gpu_info
    gpu_info="$(docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 \
        nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || true)"

    if [ -n "$gpu_info" ]; then
        echo "    GPU detectada: $gpu_info"
        echo "    O container 'inference' deve usar CUDA automaticamente."
    else
        echo "    Nenhuma GPU NVIDIA acessível pelo Docker."
        echo "    O container 'inference' vai rodar em CPU (fallback automático, sem erro)."
    fi
    echo ""
}

print_help() {
    print_banner
cat <<'EOF'
  USO
  ───────────────────────────────────────────────────────────────────
    ./run.sh <comando> [argumentos]

  COMANDOS DISPONÍVEIS
  ───────────────────────────────────────────────────────────────────

    ┌─ PIPELINE ─────────────────────────────────────────────────────
    │
    │  up                   Sobe a inferência (wake word / Whisper /
    │                       classificador). O envio do comando ao
    │                       robô fica a cargo do go2-api (repo separado).
    │                       (checa GPU antes de subir)
    │
    └────────────────────────────────────────────────────────────────

    ┌─ UTILITÁRIOS ──────────────────────────────────────────────────
    │
    │  build                Builda todas as imagens (docker compose build)
    │  logs [servico]       Segue os logs (todos, ou de um serviço)
    │  down                 Para e remove os containers
    │  ps                   Lista containers do projeto em execução
    │  gpu-check            Checa se há GPU NVIDIA disponível pro Docker
    │  help                 Mostra esta ajuda
    │
    └────────────────────────────────────────────────────────────────

  EXEMPLOS
  ───────────────────────────────────────────────────────────────────
    ./run.sh up
    ./run.sh logs inference
    ./run.sh gpu-check
    ./run.sh down

  Documentação completa: ./README.md
  Registro de bugs/soluções: ./docs/PROBLEMAS_E_SOLUCOES.md
EOF
}

case "$CMD" in
    up)
        check_gpu
        echo "==> Subindo pipeline de inferência..."
        exec docker compose up
        ;;

    build)
        echo "==> Buildando todas as imagens..."
        exec docker compose build
        ;;

    logs)
        SERVICE="${2:-}"
        if [ -n "$SERVICE" ]; then
            echo "==> Seguindo logs de: $SERVICE"
            exec docker compose logs -f "$SERVICE"
        else
            echo "==> Seguindo logs de todos os serviços..."
            exec docker compose logs -f
        fi
        ;;

    down)
        echo "==> Parando e removendo containers..."
        exec docker compose down
        ;;

    ps)
        exec docker compose ps
        ;;

    gpu-check)
        check_gpu
        ;;

    help|-h|--help)
        print_help
        ;;

    *)
        echo "Comando desconhecido: '$CMD'"
        echo
        print_help
        exit 1
        ;;
esac