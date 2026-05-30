# Pinned Packages

This directory contains Arch Linux ARM packages that must be pinned to specific
versions to ensure PiFinder 2.5.1 works correctly, regardless of what the
Arch rolling-release system installs.

## Why pinned packages in the repo?

Arch Linux ARM is a rolling-release distribution. Some upstream package updates
introduce ABI or API changes that break PiFinder dependencies. Storing the known-
good packages here guarantees a reproducible installation.

The setup and restore scripts automatically install from this directory first,
before falling back to the pacman cache or the live repos.

---

## python-libcamera-0.7.0-3-aarch64.pkg.tar.xz

**Problem**: `python-libcamera 0.7.1+` is compiled with pybind11 `smart_holder`.
`picamera2 0.3.36` (pip, latest as of 2026-05) cannot handle the resulting
Camera objects and throws:

```
RuntimeError: Unable to convert std::shared_ptr<T> to Python when the bound
type does not use std::shared_ptr or py::smart_holder as its holder type
```

**Working combination**: `libcamera 0.7.1` (system) + `python-libcamera 0.7.0`
(this package) + `picamera2 0.3.36` (pip)

`python-libcamera 0.7.0` was built without smart_holder, is backward-compatible
with the libcamera 0.7.1 library, and produces Camera objects that picamera2
can handle.

**IgnorePkg**: The setup/restore scripts add `IgnorePkg = python-libcamera`
to `/etc/pacman.conf` so `pacman -Syu` will not upgrade this package.

**Re-evaluate when**: picamera2 releases a version that supports smart_holder
(i.e. when `Picamera2._cm.cms.cameras` works with libcamera 0.7.1+ bindings).

---

## Adding new pinned packages

When a new Arch update breaks PiFinder:
1. Find the last known-good version in `/var/cache/pacman/pkg/` or
   the Arch ARM archive
2. Copy it here
3. Update `bin/restore_after_smos_update.sh` and `pifinder_stellarmate_setup.sh`
   to install it via `pacman -U`
4. Add `IgnorePkg` entry in both scripts
5. Document the issue and working combination above
