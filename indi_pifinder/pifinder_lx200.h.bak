#pragma once

#include "lx200telescope.h"
#include <mutex>

extern std::mutex lx200CommsLock;

class PiFinderLX200 : public LX200Telescope
{
    public:
        PiFinderLX200();
        virtual ~PiFinderLX200() override = default;

        virtual const char *getDefaultName() override;

    protected:
        virtual bool Goto(double ra, double dec) override;
        virtual bool ReadScopeStatus() override;
};
