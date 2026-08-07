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

#define LX200_TIMEOUT 5 /* FD timeout in seconds - moved here (was in the .cpp) so it's visible as a default parameter value below */

class LX200_PIFINDER : public LX200Telescope
{
    public:

        LX200_PIFINDER();
        ~LX200_PIFINDER() {}

        const char *getDefaultName() override;
        bool Handshake() override;
        bool initProperties() override;
        bool ReadScopeStatus() override;
        bool Goto(double ra, double dec) override;

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
};
