/*
    10micron INDI driver

    Copyright (C) 2017 Hans Lambermont

    This library is free software; you can redistribute it and/or
    modify it under the terms of the GNU Lesser General Public
    License as published by the Free Software Foundation; either
    version 2.1 of the License, or (at your option) any later version.

    This library is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
    Lesser General Public License for more details.

    You should have received a copy of the GNU Lesser General Public
    License along with this library; if not, write to the Free Software
    Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
*/

#pragma once

#include "lx200telescope.h"

#include <cmath>
#include <ctime>

#define LX200_TIMEOUT 5 /* FD timeout in seconds - moved here (was in the .cpp) so it's visible as a default parameter value below */

class LX200_PIFINDER : public LX200Telescope
{
    public:

        LX200_PIFINDER();
        ~LX200_PIFINDER() {}

        const char *getDefaultName() override;
        bool Handshake() override;
        bool initProperties() override;
        bool updateProperties() override;
        bool ReadScopeStatus() override;
        bool Goto(double ra, double dec) override;
        bool ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n) override;

        bool sendScopeLocation() override;
        bool sendScopeTime() override;

    protected:
        void getBasicData() override;
        bool updateLocation(double latitude, double longitude, double elevation) override;
        bool updateTime(ln_date *utc, double utc_offset) override;

    private:
        int fd = -1; // short notation for PortFD/sockfd

        int setStandardProcedureWithoutRead(int fd, const char *data);
        int setStandardProcedureAndExpectChar(int fd, const char *data, const char *expect);
        int setStandardProcedureAndReturnResponse(int fd, const char *data, char *response, int max_response_length,
                                                   int timeoutSec = LX200_TIMEOUT);

        // Found live investigating #139: pos_server.py can occasionally take
        // several seconds to answer under CPU load without the connection
        // actually being dead (see that issue's own writeup). Retrying a few
        // times with a shorter per-attempt timeout - instead of one long
        // LX200_TIMEOUT-second block - keeps ReadScopeStatus() from stalling
        // the whole polling cycle on a merely-slow (not dead) reply, while
        // tolerating roughly the same total worst-case wait as before.
        int readWithRetry(const char *data, char *response, int max_response_length);

        // Polls PiFinder's own /api/current_target (the on-device push-to
        // selection - see PiFinder_Stellarmate#171) and publishes it via
        // the base class's TargetNP whenever it changes, so an external
        // Mount Bridge watching TARGET_EOD_COORD sees on-device push-to
        // targets the same way it already sees external Goto()-driven
        // ones - no change needed on the Mount Bridge side.
        void pollCurrentTarget();
        double m_lastTargetRA = std::nan("");
        double m_lastTargetDec = std::nan("");

        // Direct request (2026-09-15): Camera/IMU presence, system load and
        // Mount Type/Screen Direction used to only reach a Control Host via
        // a password-protected Control-Center-to-Control-Center HTTP proxy
        // (docs/concepts/control_host_hardware_badges_mirroring.md) - these
        // are read-only device/host facts, not admin actions, so they belong
        // on the already network-transparent INDI layer instead, same as
        // this driver's own position. Polled from PiFinder's own
        // /api/hardware_status (see diffs/server_py.diff) at a slow, rate-
        // limited cadence (pollHardwareStatus() has its own gate) - unlike
        // position, these barely ever change and the underlying check
        // (rpicam-hello/I2C scan) can occasionally take several seconds, so
        // polling it every ReadScopeStatus() tick like RA/Dec would risk
        // stalling this single-threaded driver's position updates too.
        void pollHardwareStatus();
        time_t m_lastHardwareStatusPoll = 0;

        IText HardwarePresenceT[2] {};
        ITextVectorProperty HardwarePresenceTP;

        INumber SystemLoadN[6];
        INumberVectorProperty SystemLoadNP;

        IText PiFinderOrientationT[2] {};
        ITextVectorProperty PiFinderOrientationTP;

        // Unlike the three above, this one isn't polled by this driver at
        // all - PiFinder itself has no notion of "which service mode is the
        // Control Center currently running" (that's our own gui_installer/
        // server.py's own process-orchestration state, not a PiFinder or
        // hardware fact - see the 2026-09-15 chat discussion on why this
        // stays IP_RW: the Control Center pushes updates here via ISNewText
        // whenever its own mode/role state changes, this driver just stores
        // and republishes it, so EKOS/the StellarMate App/any other INDI
        // client can see it for free without knowing anything about our
        // custom Control Center API.
        IText PiFinderModeT[5] {};
        ITextVectorProperty PiFinderModeTP;
};
