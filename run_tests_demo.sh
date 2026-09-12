#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1
source .venv/bin/activate
clear

cat <<'EOF'
        ◆   V E I L G R A P H   ◆
   on-chain graph analyzer · privacy simulator
   ═════════════════════════════════════════

   ANALYZE (trace)          OBFUSCATE (hide)
   ┌──────────┐             ┌──────────┐
   │ wallet   ├──►MERCHANT  │ wallet   │
   └──────────┘  score 100  └────┬─┬───┘
                                 │ │
                           ┌─────▼ ▼─────┐
                           │  A     B    │ split
                           └─────┬─┬─────┘
                                 ▼ ▼
                           ┌─────────────┐
                           │  MERCHANT   │ score 65
                           └─────────────┘
EOF

echo
python -m pytest -v --cov=veilgraph --cov-report=term-missing --color=yes
echo
echo "Pressione ENTER para fechar."
read
