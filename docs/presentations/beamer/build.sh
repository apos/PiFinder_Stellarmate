#!/usr/bin/env bash
# Build both the dark (default) and the light version of the deck.
set -e
cd "$(dirname "$0")"
lualatex -interaction=batchmode PFSM_overview.tex
lualatex -interaction=batchmode PFSM_overview.tex        # 2nd pass: agenda bar
lualatex -interaction=batchmode -jobname=PFSM_overview_light '\def\PFSMlightbuild{}\input{PFSM_overview}'
lualatex -interaction=batchmode -jobname=PFSM_overview_light '\def\PFSMlightbuild{}\input{PFSM_overview}'
rm -f *.aux *.log *.nav *.out *.snm *.toc
echo "wrote PFSM_overview.pdf and PFSM_overview_light.pdf"
