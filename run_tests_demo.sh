#!/usr/bin/env bash
# Testes ao vivo do veilgraph — tema BlackArch (vermelho/preto, azul no PASSED).
# Roda em loop: salve qualquer arquivo e a suite re-roda sozinha.
cd "$(dirname "$0")" || exit 1
source .venv/bin/activate

INTERVAL="${INTERVAL:-2}"

run_once() {
    clear
    python -c "from veilgraph.banner import print_banner; print_banner()"
    python -m pytest tests/ -v --color=yes --cov=veilgraph --cov-report=term-missing
    echo
    echo "  proxima execucao em ${INTERVAL}s  ·  Ctrl+C para sair"
}

if [ "${1:-}" = "--once" ]; then
    run_once
    exit $?
fi

while true; do
    run_once
    sleep "$INTERVAL"
done
