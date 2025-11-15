#include "pifinder_lx200.h"

#include "indicom.h"
#include "indiproperty.h"
#include "indilogger.h"
#include "libastro.h" // For INDI::ObservedToJ2000
#include <libnova/julian_day.h>

#include <memory>
#include <string.h>

// We declare an auto pointer to PiFinder.
std::unique_ptr<PiFinder> pifinder(new PiFinder());

PiFinder::PiFinder()
{
    setenv("INDIDEBUG", "1", 1);
}

// Helper function to send a command and get a response
bool PiFinder::SendCommand(const char *cmd, char *response, int max_len)
{
    if (pifinder_fd < 0)
        return false;

    DEBUGF(INDI::Logger::DBG_DEBUG, "CMD <%s>", cmd);
    if (write(pifinder_fd, cmd, strlen(cmd)) < 0)
    {
        DEBUGF(INDI::Logger::DBG_DEBUG, "Error writing to socket: %s", strerror(errno));
        return false;
    }

    // Wait a bit for the response
    usleep(50000);

    int bytes_read = read(pifinder_fd, response, max_len - 1);
    if (bytes_read > 0)
    {
        response[bytes_read] = '\0';
        DEBUGF(INDI::Logger::DBG_DEBUG, "RES <%s>", response);
    }
    else
    {
        response[0] = '\0';
        DEBUGF(INDI::Logger::DBG_DEBUG, "Error reading from socket%s", "");
    }
    return bytes_read > 0;
}


// Close the connection
void PiFinder::Close()
{
    if (pifinder_fd >= 0)
    {
        shutdown(pifinder_fd, SHUT_RDWR);
        close(pifinder_fd);
        pifinder_fd = -1;
    }
}

const char *PiFinder::getDefaultName()
{
    return "PiFinder";
}

bool PiFinder::Handshake()
{
    struct sockaddr_in server_addr;

    pifinder_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (pifinder_fd < 0)
    {
        DEBUGF(INDI::Logger::DBG_DEBUG, "Error creating socket: %s", strerror(errno));
        return false;
    }

    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(4030);
    server_addr.sin_addr.s_addr = inet_addr("127.0.0.1");

    if (connect(pifinder_fd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0)
    {
        DEBUGF(INDI::Logger::DBG_DEBUG, "Error connecting to PiFinder: %s", strerror(errno));
        Close();
        return false;
    }

    DEBUGF(INDI::Logger::DBG_SESSION, "Connected to PiFinder on fd %d", pifinder_fd);
    return true;
}

bool PiFinder::ReadScopeStatus()
{
    if (pifinder_fd < 0)
        return false;

    char response[32];
    int h, m, s, d;
    double jnow_ra = 0, jnow_dec = 0;

    // Get RA
    if (SendCommand(":GR#", response, sizeof(response)))
    {
        if (sscanf(response, "%d:%d:%d#", &h, &m, &s) == 3)
        {
            jnow_ra = h + m / 60.0 + s / 3600.0;
        }
    }

    // Get Dec
    if (SendCommand(":GD#", response, sizeof(response)))
    {
        if (sscanf(response, "%d*%d'%d#", &d, &m, &s) == 3)
        {
            jnow_dec = d + m / 60.0 + s / 3600.0;
            if (response[0] == '-')
                jnow_dec = -jnow_dec;
        }
    }

    // Convert from JNow to J2000
    INDI::IEquatorialCoordinates jnow_coords, j2000_coords;
    jnow_coords.rightascension = jnow_ra;
    jnow_coords.declination = jnow_dec;

    // Get current Julian date
    double jd = ln_get_julian_from_sys();

    // Precess from JNow to J2000 using INDI's internal function
    INDI::ObservedToJ2000(&jnow_coords, jd, &j2000_coords);

    EqN[0].value = j2000_coords.rightascension;
    EqN[1].value = j2000_coords.declination;

    // Update the property
    IDSetNumber(&EqNP, nullptr);

    return true;
}

bool PiFinder::initProperties()
{
    // Init properties defined in parent
    LX200Telescope::initProperties();
    return true;
}

bool PiFinder::updateProperties()
{
    // Update properties defined in parent
    LX200Telescope::updateProperties();
    return true;
}

void PiFinder::ISGetProperties(const char *dev)
{
    // Get properties defined in parent
    LX200Telescope::ISGetProperties(dev);
}

bool PiFinder::ISNewSwitch(const char *dev, const char *name, ISState *states, char *names[], int n)
{
    if (strcmp(name, Connection.name) == 0)
    {
        ISwitch *connectSwitch = IUFindSwitch(&Connection, "CONNECT");
        if (connectSwitch && connectSwitch->s == ISS_ON)
        {
            if (Handshake())
            {
                Connection.s = IPS_OK;
                Connection.sw[0].s = ISS_ON;
                Connection.sw[1].s = ISS_OFF;
            }
            else
            {
                Connection.s = IPS_ALERT;
                Connection.sw[0].s = ISS_OFF;
                Connection.sw[1].s = ISS_ON;
            }
        }
        else
        {
            Close();
            Connection.s = IPS_OK;
            Connection.sw[0].s = ISS_OFF;
            Connection.sw[1].s = ISS_ON;
        }
        IDSetSwitch(&Connection, nullptr);
        // Do not call parent, we handle connection here
        return true;
    }
    return LX200Telescope::ISNewSwitch(dev, name, states, names, n);
}

bool PiFinder::ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n)
{
    return LX200Telescope::ISNewText(dev, name, texts, names, n);
}

bool PiFinder::ISNewNumber(const char *dev, const char *name, double *values, char *names[], int n)
{
    if (strcmp(name, EqNP.name) == 0)
    {
        INumber *raNumber = IUFindNumber(&EquatorialEODNP, "RA");
        INumber *decNumber = IUFindNumber(&EquatorialEODNP, "DEC");

        if (raNumber == nullptr || decNumber == nullptr)
            return false;

        double ra = raNumber->value;
        double dec = decNumber->value;

        char command[64];
        char response[32];

        // Format RA
        int h = ra;
        int m = (ra - h) * 60;
        int s = (ra - h - m / 60.0) * 3600;
        snprintf(command, sizeof(command), ":Sr%02d:%02d:%02d#", h, m, s);
        SendCommand(command, response, sizeof(response));

        // Format Dec
        char sign = dec >= 0 ? '+' : '-';
        dec = fabs(dec);
        int d = dec;
        m = (dec - d) * 60;
        s = (dec - d - m / 60.0) * 3600;
        snprintf(command, sizeof(command), ":Sd%c%02d*%02d:%02d#", sign, d, m, s);
        
        EqNP.s = IPS_BUSY;
        IDSetNumber(&EqNP, nullptr);

        if (SendCommand(command, response, sizeof(response)) && response[0] == '1')
        {
            EqNP.s = IPS_OK;
            EqN[0].value = ra;
            EqN[1].value = dec;
        }
        else
        {
            EqNP.s = IPS_ALERT;
        }
        IDSetNumber(&EqNP, nullptr);
        return true;
    }

    return LX200Telescope::ISNewNumber(dev, name, values, names, n);
}

bool PiFinder::ISNewBLOB(const char *dev, const char *name, int sizes[], int blobsizes[], char *blobs[], char *formats[], char *names[], int n)
{
    // We call the parent method
    return LX200Telescope::ISNewBLOB(dev, name, sizes, blobsizes, blobs, formats, names, n);
}
