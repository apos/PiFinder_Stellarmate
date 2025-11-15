#include "pifinder_lx200.h"
#include "indicom.h"
#include "indilogger.h"
#include "lx200driver.h"

#include <memory>
#include <cstring>
#include <unistd.h>
#include <cmath>
#include <mutex>

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
    return LX200Telescope::ReadScopeStatus();
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

    // PiFinder expects a specific sequence of commands
    // 1. Set RA
    // 2. Set DEC
    // The slew is initiated by the DEC command.

    char command[64];
    int nbytes_write = 0;
    int error_type;
    int h, m, s, d;

    // Set RA
    getSexComponents(ra, &h, &m, &s);
    snprintf(command, sizeof(command), ":Sr%02d:%02d:%02d#", h, m, s);
    {
        std::unique_lock<std::mutex> guard(lx200CommsLock);
        if ((error_type = tty_write_string(PortFD, command, &nbytes_write)) != TTY_OK)
        {
            LOGF_ERROR("Goto RA command failed: %s", command);
            return false;
        }
    }

    // Set DEC
    // Custom format for DEC: ":Sd+DD*MM:SS#"
    char sign = (dec >= 0) ? '+' : '-';
    double abs_dec = std::abs(dec);
    getSexComponents(abs_dec, &d, &m, &s);
    snprintf(command, sizeof(command), ":Sd%c%02d*%02d:%02d#", sign, d, m, s);
    {
        std::unique_lock<std::mutex> guard(lx200CommsLock);
        if ((error_type = tty_write_string(PortFD, command, &nbytes_write)) != TTY_OK)
        {
            LOGF_ERROR("Goto DEC command failed: %s", command);
            return false;
        }
    }

    TrackState = SCOPE_SLEWING;
    LOGF_INFO("Slewing to RA: %s - DEC: %s", RAStr, DecStr);

    return true;
}