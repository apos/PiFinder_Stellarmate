#include "pifinder_lx200.h"

#include <libnova/julian_day.h>
#include <libnova/transform.h>

#include "indicom.h"
#include "indiproperty.h"
#include "indilogger.h"

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
    struct ln_equ_posn jnow_coords, j2000_coords;
    jnow_coords.ra = jnow_ra;
    jnow_coords.dec = jnow_dec;

    // Get current Julian date
    double jd = ln_get_julian_from_sys();

    // Precess from JNow to J2000
    ln_precess_equ(&jnow_coords, jd, J2000);
    j2000_coords = jnow_coords;

    EquatorialEODN[0].value = j2000_coords.ra;
    EquatorialEODN[1].value = j2000_coords.dec;

    // Update the property
    IDSetNumber(&EquatorialEODNP, nullptr);

    return true;
}

bool PiFinder::initProperties()
{
    // Init properties defined in parent
    INDI::DefaultDevice::initProperties();

    // Initialize properties
    IUFillSwitch(&ConnectionS[0], "CONNECT", "Connect", ISS_OFF);
    IUFillSwitch(&ConnectionS[1], "DISCONNECT", "Disconnect", ISS_ON);
    IUFillSwitchVector(&ConnectionSP, ConnectionS, 2, getDeviceName(), "CONNECTION", "Connection", MAIN_CONTROL_TAB, IP_RW, ISR_1OFMANY, 0, IPS_IDLE);

    IUFillNumber(&EquatorialEODN[0], "RA", "RA", "%02.0f:%02.0f:%04.1f", 0, 24, 0, 0);
    IUFillNumber(&EquatorialEODN[1], "DEC", "Dec", "%+02.0f:%02.0f:%02.0f", -90, 90, 0, 0);
    IUFillNumberVector(&EquatorialEODNP, EquatorialEODN, 2, getDeviceName(), "EQUATORIAL_EOD_COORD", "RA/DEC J2000", MAIN_CONTROL_TAB, IP_RW, 0, IPS_IDLE);

    IUFillNumber(&HorizontalCoordinatesN[0], "ALT", "Altitude", "%+02.0f:%02.0f:%02.0f", -90, 90, 0, 0);
    IUFillNumber(&HorizontalCoordinatesN[1], "AZ", "Azimuth", "%03.0f:%02.0f:%02.0f", 0, 360, 0, 0);
    IUFillNumberVector(&HorizontalCoordinatesNP, HorizontalCoordinatesN, 2, getDeviceName(), "HORIZONTAL_COORDINATES", "Alt/Az", MAIN_CONTROL_TAB, IP_RO, 0, IPS_IDLE);

    // Tell INDI this is a Telescope
    setDriverInterface(TELESCOPE_INTERFACE);

    // Add the properties to the driver
    defineProperty(&ConnectionSP);
    defineProperty(&EquatorialEODNP);

    return true;
}

bool PiFinder::updateProperties()
{
    // Update properties defined in parent
    INDI::DefaultDevice::updateProperties();

    if (isConnected())
    {
        // We are connected, so we are ready to receive commands
        defineProperty(&HorizontalCoordinatesNP);
    }
    else
    {
        // We are not connected, so we cannot receive commands
        deleteProperty(HorizontalCoordinatesNP.name);
    }

    return true;
}

void PiFinder::ISGetProperties(const char *dev)
{
    // Get properties defined in parent
    INDI::DefaultDevice::ISGetProperties(dev);
}

bool PiFinder::ISNewSwitch(const char *dev, const char *name, ISState *states, char *names[], int n)
{
    if (strcmp(name, ConnectionSP.name) == 0)
    {
        ISwitch *connectSwitch = IUFindSwitch(&ConnectionSP, "CONNECT");
        if (connectSwitch && connectSwitch->s == ISS_ON)
        {
            if (Handshake())
            {
                ConnectionSP.s = IPS_OK;
                ConnectionS[0].s = ISS_ON;
                ConnectionS[1].s = ISS_OFF;
            }
            else
            {
                ConnectionSP.s = IPS_ALERT;
                ConnectionS[0].s = ISS_OFF;
                ConnectionS[1].s = ISS_ON;
            }
        }
        else
        {
            Close();
            ConnectionSP.s = IPS_OK;
            ConnectionS[0].s = ISS_OFF;
            ConnectionS[1].s = ISS_ON;
        }
        IDSetSwitch(&ConnectionSP, nullptr);
    }
    return INDI::DefaultDevice::ISNewSwitch(dev, name, states, names, n);
}

bool PiFinder::ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n)
{
    if (strcmp(name, HorizontalCoordinatesNP.name) == 0)
    {
        double alt, az;
        if (sscanf(texts[0], "%lf", &alt) == 1 && sscanf(texts[1], "%lf", &az) == 1)
        {
            HorizontalCoordinatesN[0].value = alt;
            HorizontalCoordinatesN[1].value = az;
            HorizontalCoordinatesNP.s = IPS_OK;
        }
        else
        {
            HorizontalCoordinatesNP.s = IPS_ALERT;
        }
        IDSetNumber(&HorizontalCoordinatesNP, nullptr);
        return true;
    }
    return INDI::DefaultDevice::ISNewText(dev, name, texts, names, n);
}

bool PiFinder::ISNewNumber(const char *dev, const char *name, double *values, char *names[], int n)
{
    if (strcmp(name, EquatorialEODNP.name) == 0)
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
        
        EquatorialEODNP.s = IPS_BUSY;
        IDSetNumber(&EquatorialEODNP, nullptr);

        if (SendCommand(command, response, sizeof(response)) && response[0] == '1')
        {
            EquatorialEODNP.s = IPS_OK;
            EquatorialEODN[0].value = ra;
            EquatorialEODN[1].value = dec;
        }
        else
        {
            EquatorialEODNP.s = IPS_ALERT;
        }
        IDSetNumber(&EquatorialEODNP, nullptr);
        return true;
    }

    if (strcmp(name, HorizontalCoordinatesNP.name) == 0)
    {
        INumber *altNumber = IUFindNumber(&HorizontalCoordinatesNP, "ALT");
        INumber *azNumber = IUFindNumber(&HorizontalCoordinatesNP, "AZ");

        if (altNumber)
            HorizontalCoordinatesN[0].value = altNumber->value;
        if (azNumber)
            HorizontalCoordinatesN[1].value = azNumber->value;
        
        HorizontalCoordinatesNP.s = IPS_OK;
        IDSetNumber(&HorizontalCoordinatesNP, nullptr);
        return true;
    }

    return INDI::DefaultDevice::ISNewNumber(dev, name, values, names, n);
}

bool PiFinder::ISNewBLOB(const char *dev, const char *name, int sizes[], int blobsizes[], char *blobs[], char *formats[], char *names[], int n)
{
    // We call the parent method
    return INDI::DefaultDevice::ISNewBLOB(dev, name, sizes, blobsizes, blobs, formats, names, n);
}