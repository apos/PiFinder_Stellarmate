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

PiFinder::PiFinder() : LX200Telescope()
{
    setenv("INDIDEBUG", "1", 1);
    SetTelescopeCapability(TELESCOPE_CAN_GOTO | TELESCOPE_HAS_LOCATION | TELESCOPE_HAS_TIME, 0);
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

    // Update the inherited RaN and DecN members. The base class will update the property.
    this->EqN[0].value = j2000_coords.rightascension;
    this->EqN[1].value = j2000_coords.declination;

    return true;
}

bool PiFinder::initProperties()
{
    // Init properties defined in parent
    LX200Telescope::initProperties();

    // Initialize our custom properties
    IUFillNumber(&HorizontalCoordinatesN[0], "ALT", "Altitude", "%+02.0f:%02.0f:%02.0f", -90, 90, 0, 0);
    IUFillNumber(&HorizontalCoordinatesN[1], "AZ", "Azimuth", "%03.0f:%02.0f:%02.0f", 0, 360, 0, 0);
    IUFillNumberVector(&HorizontalCoordinatesNP, HorizontalCoordinatesN, 2, getDeviceName(), "HORIZONTAL_COORDINATES", "Alt/Az", MAIN_CONTROL_TAB, IP_RO, 0, IPS_IDLE);

    // Add our custom properties to the driver
    defineProperty(&HorizontalCoordinatesNP);

    return true;
}

bool PiFinder::updateProperties()
{
    // Update properties defined in parent
    LX200Telescope::updateProperties();

    if (isConnected())
    {
        defineProperty(&HorizontalCoordinatesNP);
    }
    else
    {
        deleteProperty(HorizontalCoordinatesNP.name);
    }

    return true;
}

void PiFinder::ISGetProperties(const char *dev)
{
    // Get properties defined in parent
    LX200Telescope::ISGetProperties(dev);
}

bool PiFinder::ISNewSwitch(const char *dev, const char *name, ISState *states, char *names[], int n)
{
    // Let the parent class handle all switch changes, including Connection.
    // It will call our overridden Handshake() method when needed.
    return LX200Telescope::ISNewSwitch(dev, name, states, names, n);
}

bool PiFinder::ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n)
{
    // Handle our custom properties
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
    // Pass everything else to the parent class
    return LX200Telescope::ISNewText(dev, name, texts, names, n);
}

bool PiFinder::ISNewNumber(const char *dev, const char *name, double *values, char *names[], int n)
{
    // Handle our custom properties
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

    // Pass everything else to the parent class. It will handle EqNP and call GoTo().
    return LX200Telescope::ISNewNumber(dev, name, values, names, n);
}

bool PiFinder::ISNewBLOB(const char *dev, const char *name, int sizes[], int blobsizes[], char *blobs[], char *formats[], char *names[], int n)
{
    // We call the parent method
    return LX200Telescope::ISNewBLOB(dev, name, sizes, blobsizes, blobs, formats, names, n);
}