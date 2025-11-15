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

PiFinderLX200::PiFinderLX200() : LX200Telescope()
{
    // Constructor
}

const char *PiFinderLX200::getDefaultName()
{
    return "PiFinder LX200";
}

bool PiFinderLX200::Handshake()
{
    // PiFinder's pos_server.py does not respond to a simple ACK (0x06).
    // Instead, it expects LX200 commands directly. We'll send a :GR# command
    // to get the current RA, which will also serve as a handshake.
#define MAX_RESPONSE_SIZE 80
#define LX200_TIMEOUT 5 /* FD timeout in seconds */

    char command[] = ":GR#";
    char response[MAX_RESPONSE_SIZE];
    int nbytes_write = 0;
    int nbytes_read = 0;
    int error_type;

    LOGF_INFO("Sending initial handshake command: %s", command);

    // Use the global mutex for thread-safe serial communication
    std::unique_lock<std::mutex> guard(lx200CommsLock);
    if ((error_type = tty_write_string(PortFD, command, &nbytes_write)) != TTY_OK)
    {
        LOGF_ERROR("Initial handshake (GR) command failed: %s", command);
        Disconnect();
        return false;
    }

    // Wait for a response from the PiFinder
    if ((error_type = tty_read_section(PortFD, response, '#', LX200_TIMEOUT, &nbytes_read)) != TTY_OK)
    {
        LOG_ERROR("No response to initial handshake (GR) command.");
        Disconnect();
        return false;
    }

    LOGF_INFO("Received response to handshake: %s", response);

    // If we got a response, assume connection is established.
    // The actual parsing of RA will happen in ReadScopeStatus.
    return true;
}

bool PiFinderLX200::ReadScopeStatus()
{
    char command[] = ":GR#"; // Command to get RA
    char RAResponse[MAX_RESPONSE_SIZE];
    int nbytes_write = 0;
    int nbytes_read = 0;
    int error_type;

    // Use the global mutex for thread-safe serial communication
    std::unique_lock<std::mutex> guard(lx200CommsLock);

    // Get RA
    if ((error_type = tty_write_string(PortFD, command, &nbytes_write)) != TTY_OK)
    {
        LOGF_ERROR("ReadScopeStatus RA command failed: %s", command);
        return false;
    }
    if ((error_type = tty_read_section(PortFD, RAResponse, '#', LX200_TIMEOUT, &nbytes_read)) != TTY_OK)
    {
        LOG_ERROR("No response to ReadScopeStatus RA command.");
        return false;
    }

    // Get DEC
    char dec_command[] = ":GD#"; // Command to get DEC
    char DecResponse[MAX_RESPONSE_SIZE];
    if ((error_type = tty_write_string(PortFD, dec_command, &nbytes_write)) != TTY_OK)
    {
        LOGF_ERROR("ReadScopeStatus DEC command failed: %s", dec_command);
        return false;
    }
    if ((error_type = tty_read_section(PortFD, DecResponse, '#', LX200_TIMEOUT, &nbytes_read)) != TTY_OK)
    {
        LOG_ERROR("No response to ReadScopeStatus DEC command.");
        return false;
    }

    // The PiFinder returns strings with a trailing '#', which the standard
    // INDI LX200 parsing functions cannot handle. We need to strip it.
    char *hash_ptr = strchr(RAResponse, '#');
    if (hash_ptr != nullptr)
        *hash_ptr = '\0';

    hash_ptr = strchr(DecResponse, '#');
    if (hash_ptr != nullptr)
        *hash_ptr = '\0';

    double ra_val, dec_val;
    if (f_scansexa(RAResponse, &ra_val) == -1)
    {
        LOG_ERROR("Error parsing RA string from mount.");
        return false;
    }
    if (f_scansexa(DecResponse, &dec_val) == -1)
    {
        LOG_ERROR("Error parsing DEC string from mount.");
        return false;
    }

    NewRaDec(ra_val, dec_val);

    return true;
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