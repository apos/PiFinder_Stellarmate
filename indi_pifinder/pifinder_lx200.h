#pragma once

#include "lx200generic.h"

class PiFinderLX200 : public LX200Generic
{
    public:
        PiFinderLX200();
        virtual ~PiFinderLX200() override = default;

        virtual const char *getDefaultName() override;

    protected:
        virtual bool Goto(double ra, double dec) override;
        virtual bool ReadScopeStatus() override;
};
