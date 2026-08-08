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

    private:
        // Wherever it was last Sync'd/GoTo'd to - defaults to RA 0h/Dec 0deg
        // (same "obviously a placeholder, not a real position" convention
        // used elsewhere in this project, e.g. pos_server.py's invalid-signal
        // fix in #107) until the user sets something real.
        double m_currentRA = 0.0;
        double m_currentDEC = 0.0;

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
