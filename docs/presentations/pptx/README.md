# PowerPoint version of the PFSM overview deck

`PFSM_overview.pptx` — a multi-part overview of PiFinder_Stellarmate for **PiFinder
and StellarMate developers** (they know their own stacks — the deck covers only
what PFSM adds between them), plus a few plain-language "for dummies" slides.

Parts: project summary & focus · the Control Center · PF LX200 & Mount Bridge ·
PF Simulator. Closes on two asks — where PiFinder could take PRs
(`docs/upstream_patch_inventory.md`), and how the SMOS app could drive PFSM
(`docs/concepts/mount_bridge_web_integration.md`).

31 slides, 16:9.

## Regenerating

`build.py` builds the `.pptx` from scratch with `python-pptx`. It reads screenshots
from `../../images/` and pre-cropped regions from `assets/` (see `assets/README.md`).
Edit the slide content in `build.py`, then:

```bash
python3 -m venv .venv && .venv/bin/pip install python-pptx pillow
.venv/bin/python build.py            # writes PFSM_overview.pptx
```

The `.venv/` is git-ignored — do not commit it.

To preview as PDF/images (needs LibreOffice):

```bash
soffice --headless --convert-to pdf PFSM_overview.pptx
```

## Keeping it in sync with the Beamer version

`../beamer/` holds a LaTeX Beamer version of the same content. When the deck's
content changes, update both. Visual polish is done here in PowerPoint/Keynote;
if you hand-edit the `.pptx`, note that the next `build.py` run overwrites it.
