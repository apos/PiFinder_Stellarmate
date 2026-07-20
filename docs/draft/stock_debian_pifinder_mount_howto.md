# Draft: Connecting a real mount on stock (Debian-based) PiFinder

> **Status: concept / draft — not yet reviewed, tested, or promoted into the main documentation.**
> Written up in response to a support question (how would someone on the *original*, Debian-based
> PiFinder image connect a real mount, without any of this project's StellarMate-specific tooling).
> Kept here as a draft so the text isn't lost, pending a decision on whether/where to publish it
> properly (its own doc in `Readme_PiFinder_LX200.md`'s "See Also" section, a PR to upstream
> `brickbots/PiFinder`, a forum/Discord post, or left as-is). Tracked as
> [Issue #37](https://github.com/apos/PiFinder_Stellarmate/issues/37) ("concept" label) on the
> project board — update that issue's status if this draft gets promoted or dropped.

## Context

[Readme_PiFinder_LX200.md](../../Readme_PiFinder_LX200.md) assumes a StellarMate-managed install,
where `libindi-dev` and a Web Manager already exist. A stock PiFinder image (Raspberry Pi OS) has
neither preinstalled — someone on vanilla PiFinder needs a few extra setup steps before the existing
LX200/Mount Bridge walkthrough (Steps 2–5) applies unchanged.

## 0. Prerequisites

- **`cmake` and a C++ compiler** (`build-essential` on Debian/Raspberry Pi OS pulls in `g++`/`cpp`,
  `make`, and the other standard build tools) — needed to compile the PiFinder LX200/Mount Bridge
  drivers in step 3 below. This is the same requirement `Readme_PiFinder_LX200.md`'s own
  Prerequisites section lists for the StellarMate path; on stock Debian it just isn't preinstalled,
  so it's spelled out explicitly here rather than assumed.
- **`libindi-dev`** (the actual INDI development headers/libraries the drivers link against —
  `libindilx200`, `libindidriver`) — covered in step 1 below, since it comes from the same apt
  install as the rest of the INDI stack.
- **`git`** (already on any PiFinder image, used to clone the driver source in step 3).

## 1. Install a full INDI stack (with dev headers)

Raspberry Pi OS's own repos usually only carry `libindi1`/`indi-bin` (runtime only, no headers,
often outdated). Add INDI's own recommended Raspberry Pi repository (maintained by Radek
Kaczorek/Astroberry, arm64+armhf builds) — **not** Jasem Mutlaq's `ppa:mutlaqja/ppa`, which is
Ubuntu-only and won't resolve cleanly on Raspberry Pi OS:

```bash
curl -fsSL https://astroberry.io/debian/astroberry.asc | sudo gpg --dearmor -o /etc/apt/keyrings/astroberry.gpg
curl -fsSL https://astroberry.io/debian/astroberry.sources | sudo tee /etc/apt/sources.list.d/astroberry.sources
sudo apt update
sudo apt install indi-full libindi-dev cmake build-essential
```

`libindi-dev` is the important one here — it's what lets you compile the PiFinder LX200/Mount
Bridge drivers against the system's own INDI libraries (`libindilx200`, `libindidriver`), no full
INDI source checkout needed.

## 2. Install the INDI Web Manager

Stock PiFinder has no Web Manager either — the open-source project it's built on (`indiwebmanager`,
the same code StellarMate's own Web Manager is a branded fork of) installs cleanly via pip:

```bash
sudo pip install indiweb
git clone https://github.com/knro/indiwebmanager.git /tmp/indiwebmanager
sudo cp /tmp/indiwebmanager/indiwebmanager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now indiwebmanager.service
```

Edit `/etc/systemd/system/indiwebmanager.service` first if your login user isn't `pi`. Once running,
it listens on **port 8624**, same as StellarMate's own — `http://<pi-address>:8624` in a browser.

## 3. Build and install the PiFinder LX200 / Mount Bridge drivers

The driver source lives in this repo (`indi_pifinder/`, `indi_pifinder_bridge/`) — only those two
folders plus the two build scripts are needed, not the rest of this project's StellarMate-specific
tooling:

```bash
git clone https://github.com/apos/PiFinder_Stellarmate.git
cd PiFinder_Stellarmate
bash bin/build_indi_driver.sh     # PiFinder LX200
bash bin/build_indi_bridge.sh     # PiFinder Mount Bridge (only if you want to couple a real mount)
```

Both scripts link directly against the system `libindi` installed in step 1, install the built
binaries to `/usr/bin/`, and register them in `/usr/share/indi/drivers.xml` automatically. If Web
Manager was already running when you did this, restart it once so it picks up the new entries:
`sudo systemctl restart indiwebmanager.service`.

## 4. Everything from here on is identical to the StellarMate walkthrough

Once INDI + Web Manager + the drivers are in place, the rest doesn't depend on StellarMate at all —
follow [Readme_PiFinder_LX200.md](../../Readme_PiFinder_LX200.md) starting at
[Step 2](../../Readme_PiFinder_LX200.md#step-2-create-an-equipment-profile-in-the-web-manager):

- Step 2: create the Equipment Profile in Web Manager (PiFinder LX200 + your real mount's driver,
  e.g. an OnStep/EQMod/whatever driver applies)
- Step 3: connect both in the INDI Control Panel
- Step 4: point KStars/Ekos at it in **Remote Host** mode (critical — Local mode won't find these
  drivers, they're not in Ekos's own bundled catalog)
- Step 5: SkySafari via the `indi_skysafari` bridge on port 9624, if wanted

Those four steps are pure INDI/Ekos mechanics, unrelated to which OS built the drivers.

## Sources checked while drafting this

- <https://docs.indilib.org/getting-started/>
- <https://www.indilib.org/download/raspberry-pi/category/6-raspberry-pi.html>
- <https://github.com/knro/indiwebmanager/blob/master/README.md>
- <https://github.com/rkaczorek/astroberry-server>

## Open items before this can be promoted out of draft status

- Not yet tested end-to-end on a real stock PiFinder image — only cross-checked against current
  upstream docs, none of it run against real hardware yet.
- Decide on a permanent home: fold into `Readme_PiFinder_LX200.md` as an OS-specific prerequisites
  variant, keep as a standalone doc, or propose upstream to `brickbots/PiFinder` directly (their own
  docs don't currently cover connecting a real mount at all).
