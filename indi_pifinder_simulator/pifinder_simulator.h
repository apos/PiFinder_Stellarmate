/*
    PiFinder Simulator

    A purpose-built, deliberately dumb "position pinboard" INDI telescope
    device - not a copy of INDI's own stock Telescope Simulator (which is
    already used, unmodified, as the *mount* side of a simulated setup - see
    basic-memory pifinder-stellarmate/00164 concept notes). This device is the
    other, independent half: a precisely and manually settable RA/Dec that a
    small glue tool (test_tools/) reads and injects into PiFinder as a fixed
    "sky truth" via PiFinder's existing /api/fake_solve endpoint, refreshed
    every poll cycle so the freshness gate never lapses.

    Deliberately has no simulated slew time and no drift of its own - Sync and
    Goto both just take effect immediately and stay exactly there until
    changed again, so whoever is using it always knows precisely where
    PiFinder is meant to be "looking" for the test in progress. Named
    distinctly from "Telescope Simulator" so both can be added to the same
    EKOS profile at once without colliding in device-selection lists.

    No physical connection of any kind (CONNECTION_NONE) - it is a pure
    in-memory value holder, nothing to open/close.

    This library is free software; you can redistribute it and/or
    modify it under the terms of the GNU Lesser General Public
    License as published by the Free Software Foundation; either
    version 2.1 of the License, or (at your option) any later version.

    This library is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
    Lesser General Public License for more details.
*/

#pragma once

#include "inditelescope.h"

#include <string>

class PiFinderSimulator : public INDI::Telescope
{
    public:
        PiFinderSimulator();
        ~PiFinderSimulator() override = default;

        const char *getDefaultName() override;

    protected:
        bool initProperties() override;
        bool updateProperties() override;
        bool saveConfigItems(FILE *fp) override;
        bool Connect() override;
        bool Disconnect() override;
        bool ReadScopeStatus() override;
        bool Goto(double ra, double dec) override;
        bool Sync(double ra, double dec) override;
        bool ISNewNumber(const char *dev, const char *name, double values[], char *names[], int n) override;
        bool ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n) override;

        // §9, docs/concepts/complete_position_simulator.md (2026-09-01): while
        // MountDeviceTP names a real device and it reports EQUATORIAL_EOD_COORD
        // state Busy (an actual slew in progress), this device's own position
        // follows it live - physically accurate, since a real PiFinder is
        // rigidly bolted to the OTA and moves with any real mount movement.
        // Once the mount goes idle again, this device holds its own
        // now-updated position independently, same as always - it does NOT
        // keep following further mount-side drift after the slew ends, which
        // would defeat the whole point of having an independent truth (see
        // the class comment and 00092/00164/#177 in basic-memory
        // pifinder-stellarmate). Falls through to the base class for
        // INDI::Telescope's own GPS/Dome snooping (addAuxControls()) on
        // anything that isn't our watched mount device.
        bool ISSnoopDevice(XMLEle *root) override;

        // Simple, explicit poll loop - see Connect()'s own comment for why
        // this exists (the real bug was Connect() never calling SetTimer()
        // at all, not anything TimerHit()-specific) - kept as our own
        // override anyway so the loop's behavior doesn't depend on
        // undocumented INDI::Telescope::TimerHit() internals (source
        // unavailable on this system, headers only).
        void TimerHit() override;

    private:
        // Wherever it was last Sync'd/GoTo'd to - starts at a fixed, sensible
        // above-the-horizon default (see m_hasPosition below), not 0h/0deg.
        double m_currentRA = 5.5;
        double m_currentDEC = 20.0;

        // Direct reversal, 2026-09-01, of an earlier same-session fix that
        // started this device with NO position (m_hasPosition=false,
        // EqNP left at IPS_IDLE - see git history) - modeled after
        // PiFinder/pos_server.py's own #107 "never fake a placeholder
        // position" principle, which is right for that file (a REAL
        // PiFinder's actual GPS/solve state) but wrong here: this is a
        // Full-Simulation TEST fixture, not real hardware, and starting it
        // "empty" just meant every single restart needed a manual re-seed
        // before Full Simulation was usable at all - the truth-injector
        // faithfully forwarded that "no position yet" through to PiFinder
        // LX200, producing an obviously-bogus 0/0 mismatch against the
        // mount that looked exactly like a real bug. Direct feedback: "Er
        // muss einen sinnvollen Wert über dem Horizont einnehmen... Alles
        // andere ist nicht akzeptabel" - this device must always be
        // immediately usable. TelSim (the mount) staying wherever it was is
        // fine and expected on its own - the user decides whether/how to
        // correct that (Coupling presets, manual Sync) - this field is only
        // about PiFinder's own side always being ready.
        bool m_hasPosition = true;

        // 2026-09-01: a *fixed* compiled-in RA/Dec (whatever it's set to)
        // can never actually guarantee "above the horizon" - it depends on
        // time and location, and this test rig's own GPS/time genuinely put
        // 5.5h/20deg below the horizon live (see Connect()'s own comment
        // and pickSafeDefaultPosition() in the .cpp) - direct user feedback:
        // sending a real mount there would be unsafe. Connect() replaces the
        // compiled-in value with a real, currently-visible star exactly
        // once per process lifetime (not on every reconnect, and never once
        // a real Sync()/Goto() has already set something deliberate).
        bool m_startupDefaultReplaced = false;

        // Distinct from Sync()/Goto() above, which move the simulated "sky
        // truth" position itself (m_currentRA/DEC, what a test session feeds
        // PiFinder via fake_solve). This instead only updates the inherited
        // TargetNP (TARGET_EOD_COORD) - the exact same base-class mechanism
        // every real INDI::Telescope driver (including the real "PiFinder
        // LX200") populates on a genuine push-to, and exactly what Mount
        // Bridge's getPiFinderTargetRADE() watches for Fall 1 detection.
        // Lets a test session simulate a PiFinder push-to without needing
        // real PiFinder hardware/software running - see #186.
        INDI::PropertyNumber PushToTargetNP {2};

        // Which real/simulated mount device to watch for real slewing (see
        // ISSnoopDevice's own comment) - deliberately a configurable text
        // property, never hardcoded to "Telescope Simulator" (basic-memory
        // pifinder-stellarmate/00102's explicit lesson: this must work with
        // ANY mount, TelSim is only one special case). Empty by default -
        // following is off until a test session actually names a device.
        ITextVectorProperty MountDeviceTP;
        IText MountDeviceT[1] {};
        enum { MOUNT_DEVICE };
        std::string m_snoopedMountDevice;

        // Found live (2026-09-01): MountDeviceTP is only defined once
        // connected (see updateProperties()), so it has nothing to load
        // into until then - same reasoning, and same guard pattern, as
        // pifinder_mount_bridge.cpp's own m_connectedConfigLoaded. Without
        // this, a fresh Ekos/profile restart silently reset the mount-follow
        // feature back to "off" every time - discovered live when a
        // previously-working setup stopped following after a restart with
        // no config change at all.
        bool m_connectedConfigLoaded = false;

        // Snoop target for IUSnoopNumber() - shape must match the watched
        // device's own EQUATORIAL_EOD_COORD (name + RA/DEC element names)
        // for the name-matching inside IUSnoopNumber() to succeed. Never
        // defineProperty()'d - purely an internal decode buffer, not a
        // property this device itself publishes.
        INumberVectorProperty MountEqNP;
        INumber MountEqN[2];
        enum { MOUNT_AXIS_RA, MOUNT_AXIS_DE };

        // Found live (2026-09-01, basic-memory pifinder-stellarmate/00105):
        // naively following every mount Busy episode also follows Mount
        // Bridge's OWN corrective re-syncs (Auto-correct, Goto-Forward's
        // HOLDING re-sync) - this device then ends up chasing the mount's
        // own imperfect corrected landing spot instead of staying anchored,
        // a feedback loop that silently defeats drift detection entirely
        // (confirmed live: PiFinder and mount walked steadily off together,
        // never actually converging). Fix: snoop Mount Bridge's own
        // CORRECTION_AGE (see its header comment in pifinder_mount_bridge.h)
        // - unlike MountDeviceTP, this is a fixed, singular device name
        // (Mount Bridge is never renamed/swapped the way a mount driver is),
        // so hardcoding it here is correct, not a repeat of the
        // never-hardcode-the-mount lesson above. Only follow a Busy episode
        // when Mount Bridge's own age comfortably exceeds this - i.e. the
        // Busy state is NOT explained by something Mount Bridge itself just
        // sent.
        static constexpr const char *MOUNT_BRIDGE_DEVICE_NAME = "PiFinder Mount Bridge";
        static constexpr double CORRECTION_GRACE_SEC = 4.0;
        double m_mountBridgeCorrectionAge = 1e9;
        INumberVectorProperty MountBridgeCorrectionAgeNP;
        INumber MountBridgeCorrectionAgeN[1];

        // Forwarded-GoTo follow (2026-09-01, issue #177 / #232 follow-up):
        // the CORRECTION_AGE gate above correctly suppresses following Mount
        // Bridge's small HOLDING/auto-correct re-sync nudges, but in
        // Goto-Forward it *also* suppressed following the genuine forwarded
        // user GoTo (that too goes out via sendMountCoords(), bumping the
        // age) - so after a "GoTo Vega" the mount slewed to Vega while this
        // device stayed frozen at the old position, leaving a permanent
        // residual. Fix: also snoop the mount's own TARGET_EOD_COORD (the
        // standard INDI::Telescope property the base class populates on every
        // real Goto). A *change* of that target means a new slew to a new
        // place is starting - follow the mount through to it. A HOLDING
        // re-sync re-issues the *same* held target, so it does not change
        // TARGET_EOD_COORD and is still (correctly) not followed.
        INumberVectorProperty MountTargetNP;
        INumber MountTargetN[2];
        enum { MOUNT_TGT_RA, MOUNT_TGT_DE };
        // A real new target differs from the last one by far more than this;
        // a re-issued identical Goto differs by 0. ~1.2 arcmin of slack for
        // floating-point / rounding noise only.
        static constexpr double MOUNT_TARGET_CHANGE_EPS_DEG = 0.02;
        // Stop following once the mount has settled (EQ state OK) within this
        // of the new target - the exact settled position is still copied
        // verbatim, this only decides *when* to let go.
        static constexpr double FOLLOW_ARRIVED_ARCMIN = 3.0;
        // Safety net: never follow indefinitely if the mount never actually
        // slews (target set to where it already points) or never reports OK.
        static constexpr long FOLLOW_TIMEOUT_SEC = 120;
        bool m_followActive = false;
        bool m_haveLastMountTarget = false;
        double m_lastMountTargetRA = 0.0;   // hours
        double m_lastMountTargetDEC = 0.0;  // degrees
        double m_followTargetRA = 0.0;
        double m_followTargetDEC = 0.0;
        long m_followDeadline = 0;
        // Rate limit for the "rejected unusable snooped mount coordinate"
        // warning below - a persistently misbehaving upstream mount/driver
        // would otherwise spam this every ISSnoopDevice() call (same
        // reasoning/interval as pifinder_mount_bridge.cpp's own rate-limited
        // warnings, see its m_lastMaxSyncDriftWarnTime).
        static constexpr long BAD_MOUNT_COORD_WARN_INTERVAL_SEC = 45;
        long m_lastBadMountCoordWarnTime = 0;

        static double separationArcmin(double ra1_h, double dec1_d, double ra2_h, double dec2_d);
        // Root-cause fix (2026-09-05): found live pointing a real mount at
        // Dec 90 (NCP) - this device's EQUATORIAL_EOD_COORD ended up NaN
        // with no Sync()/Goto()/client write anywhere in the log to explain
        // it. The only remaining path is ISSnoopDevice() copying the
        // snooped mount's MountEqN/MountTargetN values straight into
        // m_currentRA/DEC (and separationArcmin() feeding them to acos())
        // with no validation at all - unlike every other place in this
        // codebase that ingests a live mount/PiFinder coordinate (see
        // pifinder_mount_bridge.cpp's httpGetPiFinderFreshCamPosition()
        // 0.05h/0.05deg plausibility gate, and its sendMountCoordsSafe()
        // horizon check). Whether the NaN itself originates from OnStep's
        // own alignment-subsystem math at the exact pole, a transient
        // read glitch, or something else upstream was NOT pinned down live
        // (the raw :GD# wire responses sampled afterward were clean) - but
        // this device has no business trusting external live-hardware data
        // unvalidated regardless of the exact upstream cause, so the
        // ingestion points themselves are hardened rather than guessing at
        // and patching one specific upstream trigger.
        static bool isUsableCoordinate(double ra_h, double dec_d);
};
