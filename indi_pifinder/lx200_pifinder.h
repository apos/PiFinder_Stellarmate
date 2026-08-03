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
};
