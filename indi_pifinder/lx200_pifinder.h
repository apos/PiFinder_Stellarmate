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
        int setStandardProcedureAndReturnResponse(int fd, const char *data, char *response, int max_response_length);

        // #118/#139: a dead TCP connection (e.g. pos_server.py restarting
        // under us) previously went undetected forever - ReadScopeStatus()
        // kept returning false every tick with no visible consequence, while
        // CONNECTION stayed On and the last successfully-read RA/Dec sat
        // frozen, silently lying about being live. After this many
        // consecutive read failures, force a full reconnect through the same
        // setConnected()/updateProperties() sequence the CONNECTION property
        // handler itself uses (see #139's analysis: calling the raw
        // Connect()/Disconnect() virtuals alone does NOT work - Connect()
        // early-returns true if isConnected() is still (wrongly) true, and
        // only setConnected() - which only the property handler normally
        // calls - ever flips that flag).
        int m_consecutiveReadFailures = 0;
        static constexpr int MAX_CONSECUTIVE_READ_FAILURES = 3;
        bool handleReadFailure();
};
