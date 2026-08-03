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
        void TimerHit() override;

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
        // frozen, silently lying about being live. Force a full reconnect
        // through the same setConnected()/updateProperties() sequence the
        // CONNECTION property handler itself uses (see #139's analysis:
        // calling the raw Connect()/Disconnect() virtuals alone does NOT
        // work - Connect() early-returns true if isConnected() is still
        // (wrongly) true, and only setConnected() - which only the property
        // handler normally calls - ever flips that flag).
        //
        // Live-tested finding (#139): a single threshold for every failure
        // reason was too trigger-happy. tty_nread_section()'s TTY_TIME_OUT
        // just means "no reply within LX200_TIMEOUT" - pos_server.py can be
        // briefly slow (e.g. busy with a solve) without the connection
        // actually being dead, and reconnecting over that churns a perfectly
        // healthy connection (observed live: oscillating roughly every 23s).
        // TTY_READ_ERROR/TTY_WRITE_ERROR/TTY_PORT_FAILURE, by contrast, mean
        // the OS itself reported the socket broken (e.g. ECONNRESET) - an
        // unambiguous signal that doesn't need patience. So: few consecutive
        // hard errors trigger a reconnect almost immediately, but plain
        // timeouts need many more in a row first.
        int m_consecutiveHardErrors = 0;
        int m_consecutiveTimeouts = 0;
        static constexpr int MAX_CONSECUTIVE_HARD_ERRORS = 2;
        static constexpr int MAX_CONSECUTIVE_TIMEOUTS = 10;
        bool handleReadFailure(int ttyErrorCode);

        // Live-tested finding: Telescope::TimerHit() only re-arms its own
        // SetTimer() while isConnected() is true, checked once at entry -
        // if handleReadFailure() marks us disconnected (setConnected(false,
        // ...)) and the very next Connect() attempt fails (e.g. pos_server.py
        // still restarting), Telescope::TimerHit() stops calling
        // ReadScopeStatus() forever, so nothing ever retries again. This
        // override keeps retrying Connect() itself every polling period
        // while m_autoReconnectPending is set, independently of the base
        // class's isConnected()-gated loop.
        bool m_autoReconnectPending = false;
};
