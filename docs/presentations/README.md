# Presentations

## `PFSM_overview.pptx`

A multi-part overview of PiFinder_Stellarmate for **PiFinder and StellarMate developers**
(they know their own stacks — the deck covers only what PFSM adds between them), plus a few
plain-language "for dummies" slides.

Parts: project summary & focus · the Control Center · PF LX200 & Mount Bridge · PF Simulator.
Closes on two asks — where PiFinder could take PRs (`docs/upstream_patch_inventory.md`), and how
the SMOS app could drive PFSM (`docs/concepts/mount_bridge_web_integration.md`).

30 slides, 16:9. Screenshots are pulled from `docs/images/readme/`.

### Regenerating

`build.py` builds the `.pptx` from scratch with `python-pptx`. It reads three images from
`../images/readme/`. Edit the slide content in `build.py`, then:

```bash
python3 -m venv .venv && .venv/bin/pip install python-pptx pillow
.venv/bin/python build.py            # writes PFSM_overview.pptx
```

To preview as PDF/images (needs LibreOffice):

```bash
soffice --headless --convert-to pdf PFSM_overview.pptx
```
