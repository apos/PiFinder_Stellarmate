# Beamer version of the PFSM overview deck

`PFSM_overview.tex` — the same content as `../PFSM_overview.pptx`, built on the
**AVVP e.V. Beamer template** (<https://github.com/apos/beamer_template_AVVP_eV>).

## Build

Needs a full TeX Live / MacTeX (LuaLaTeX). No `biber` step.

```bash
latexmk -lualatex PFSM_overview.tex
# or:
lualatex PFSM_overview && lualatex PFSM_overview   # 2nd pass fills the agenda bar
```

Output: `PFSM_overview.pdf`.

## What is vendored here

Copied verbatim from the template repo so the deck builds standalone:

- `tex/avvp_beamer_preamble.tex` — theme, fonts, agenda bar, footer, dark/light macros
- `fonts/` — Exo 2 (body) + Share Tech Mono (titles)
- `pics/` — AVVP logos, CC icon, dark background

Screenshots are **not** copied — `\graphicspath` in the `.tex` points at
`../assets/` and `../../images/…` in this repo.

## Keeping it in sync

The PowerPoint (`../PFSM_overview.pptx`, from `../build.py`) and this `.tex` are
maintained separately. When the deck's content changes, update both.

If the AVVP template changes upstream, re-copy `tex/ fonts/ pics/` from a fresh
checkout of `beamer_template_AVVP_eV`.
