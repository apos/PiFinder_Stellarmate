#include "pifinder_lx200.h"
#include "lx200generic.h"
#include "indicom.h"
#include "indilogger.h"

#include <memory>
#include <cstring>
#include <unistd.h>
#include <cmath>

// We declare an auto pointer to PiFinderLX200.
std::unique_ptr<PiFinderLX200> pifinderlx200(new PiFinderLX200());

PiFinderLX200::PiFinderLX200()
{
    // Constructor
}

const char *PiFinderLX200::getDefaultName()
{
    return "PiFinder LX200";
}

bool PiFinderLX200::ReadScopeStatus()
{
    // The base class implementation sends :GR# and :GD# which is what PiFinder supports.
    return LX200Generic::ReadScopeStatus();
}

bool PiFinderLX200::Goto(double ra, double dec)
{
    targetRA  = ra;
    targetDEC = dec;
    char RAStr[64] = {0}, DecStr[64] = {0};
    fs_sexa(RAStr, targetRA, 2, 3600);
    fs_sexa(DecStr, targetDEC, 2, 3600);

    // Stop any existing motion
    if (EqNP.getState() == IPS_BUSY)
    {
        Abort();
    }

    // Set target RA using our custom format for PiFinder
    char command[32];
    int ra_h = static_cast<int>(targetRA);
    double ra_m_rem = (targetRA - ra_h) * 60.0;
    int ra_m = static_cast<int>(ra_m_rem);
    double ra_s_rem = (ra_m_rem - ra_m) * 60.0;
    int ra_s = static_cast<int>(round(ra_s_rem));

    // Handle rounding up
    if (ra_s >= 60) {
        ra_s -= 60;
        ra_m++;
    }
    if (ra_m >= 60) {
        ra_m -= 60;
        ra_h++;
    }
    if (ra_h >= 24) {
        ra_h -= 24;
    }

    snprintf(command, sizeof(command), ":Sr%02d%02d%02d#", ra_h, ra_m, ra_s);

    if (lx200_command(PortFD, command, nullptr, 0, 0) != 0)
    {
        LOG_ERROR("Error setting target RA.");
        EqNP.setState(IPS_ALERT);
        EqNP.apply();
        return false;
    }

    // Set target DEC using the standard driver function
    if (setObjectDEC(PortFD, targetDEC) < 0)
    {
        LOG_ERROR("Error setting target DEC.");
        EqNP.setState(IPS_ALERT);
        EqNP.apply();
        return false;
    }

    // Initiate the slew
    int err = 0;
    if ((err = Slew(PortFD)))
    {
        LOGF_ERROR("Error Slewing to JNow RA %s - DEC %s", RAStr, DecStr);
        slewError(err);
        return false;
    }

    TrackState = SCOPE_SLEWING;
    LOGF_INFO("Slewing to RA: %s - DEC: %s", RAStr, DecStr);

    return true;
}