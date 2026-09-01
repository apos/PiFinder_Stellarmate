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

class PiFinderSimulator : public INDI::Telescope
{
    public:
        PiFinderSimulator();
        ~PiFinderSimulator() override = default;

        const char *getDefaultName() override;

    protected:
        bool initProperties() override;
        bool updateProperties() override;
        bool Connect() override;
        bool Disconnect() override;
        bool ReadScopeStatus() override;
        bool Goto(double ra, double dec) override;
        bool Sync(double ra, double dec) override;
        bool ISNewNumber(const char *dev, const char *name, double values[], char *names[], int n) override;

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
};
