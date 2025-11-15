#pragma once

#include "lx200telescope.h"
#include <mutex>

extern std::mutex lx200CommsLock;

class PiFinderLX200 : public LX200Telescope
{
public:
    PiFinderLX200();

    virtual const char *getDefaultName() override;
    virtual bool Handshake() override;
    virtual bool ReadScopeStatus() override;
    virtual bool Goto(double ra, double dec) override;
};
