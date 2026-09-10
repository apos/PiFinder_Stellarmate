# Presentations

A multi-part overview of PiFinder_Stellarmate for **PiFinder and StellarMate
developers** (they know their own stacks — the deck covers only what PFSM adds
between them), plus a few plain-language "for dummies" slides.

Parts: project summary & focus · the Control Center · PF LX200 & Mount Bridge ·
PF Simulator. Closes on two asks — where PiFinder could take PRs
(`docs/upstream_patch_inventory.md`), and how the SMOS app could drive PFSM
(`docs/concepts/mount_bridge_web_integration.md`).

Same content, two formats:

| Folder | Format | Built with | See |
|---|---|---|---|
| [`pptx/`](pptx/) | PowerPoint (`.pptx`), 16:9 | `python-pptx` via `build.py` | [`pptx/README.md`](pptx/README.md) |
| [`beamer/`](beamer/) | LaTeX Beamer (`.pdf`) on the AVVP e.V. template | LuaLaTeX | [`beamer/README.md`](beamer/README.md) |

Screenshots come from `docs/images/`; `pptx/assets/` holds a few pre-cropped
regions that both versions reference.

The two are maintained by hand — when the deck's content changes, update both.
