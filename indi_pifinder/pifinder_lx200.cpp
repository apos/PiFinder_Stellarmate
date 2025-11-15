
#include "pifinder.h"

#include "indicom.h"
#include "indiproperty.h"
#include "indilogger.h"

#include <memory>
#include <string.h>

// We declare an auto pointer to PiFinder.
std::unique_ptr<PiFinder> pifinder(new PiFinder());

PiFinder::PiFinder()
{
    // Initialize INDI properties
    // Connection switch
    ConnectionS[0].name = "CONNECT";
    ConnectionS[0].s = INDI::ISS_OFF;
    ConnectionS[1].name = "DISCONNECT";
    ConnectionS[1].s = INDI::ISS_ON;
    this->ConnectionSP.np = this->ConnectionS;
    ConnectionSP.name = "CONNECTION";
    ConnectionSP.label = "Connection";
    ConnectionSP.type = INDI::IPS_CS_EQ_CONJ;
    ConnectionSP.access = INDI::IP_RW;
    ConnectionSP.state = INDI::IPS_IDLE;
    ConnectionSP.perm = INDI::IP_RW;
    ConnectionSP.rule = INDI::ISR_1OF2;
    ConnectionSP.aux = "Main";
    ConnectionSP.nnp = 2;

    // Equatorial coordinates
    EquatorialEODN[0].name = "RA";
    EquatorialEODN[0].label = "Right Ascension";
    EquatorialEODN[0].format = "%02.0f:%02.0f:%04.1f";
    EquatorialEODN[0].min = 0;
    EquatorialEODN[0].max = 24;
    EquatorialEODN[0].step = 0;
    EquatorialEODN[0].value = 0;

    EquatorialEODN[1].name = "DEC";
    EquatorialEODN[1].label = "Declination";
    EquatorialEODN[1].format = "%+02.0f:%02.0f:%02.0f";
    EquatorialEODN[1].min = -90;
    EquatorialEODN[1].max = 90;
    EquatorialEODN[1].step = 0;
    EquatorialEODN[1].value = 0;

    this->EquatorialEODNP.np = this->EquatorialEODN;
    EquatorialEODNP.name = "EQUATORIAL_EOD_COORD";
    EquatorialEODNP.label = "RA/DEC J2000";
    EquatorialEODNP.type = INDI::IP_NUMBER;
    EquatorialEODNP.access = INDI::IP_RW;
    EquatorialEODNP.state = INDI::IPS_IDLE;
    EquatorialEODNP.perm = INDI::IP_RW;
    EquatorialEODNP.nnp = 2;

    // Horizontal coordinates (for display, not control)
    HorizontalCoordinatesN[0].name = "ALT";
    HorizontalCoordinatesN[0].label = "Altitude";
    HorizontalCoordinatesN[0].format = "%+02.0f:%02.0f:%02.0f";
    HorizontalCoordinatesN[0].min = -90;
    HorizontalCoordinatesN[0].max = 90;
    HorizontalCoordinatesN[0].step = 0;
    HorizontalCoordinatesN[0].value = 0;

    HorizontalCoordinatesN[1].name = "AZ";
    HorizontalCoordinatesN[1].label = "Azimuth";
    HorizontalCoordinatesN[1].format = "%03.0f:%02.0f:%02.0f";
    HorizontalCoordinatesN[1].min = 0;
    HorizontalCoordinatesN[1].max = 360;
    HorizontalCoordinatesN[1].step = 0;
    HorizontalCoordinatesN[1].value = 0;

    this->HorizontalCoordinatesNP.np = this->HorizontalCoordinatesN;
    HorizontalCoordinatesNP.name = "HORIZONTAL_COORDINATES";
    HorizontalCoordinatesNP.label = "Alt/Az";
    HorizontalCoordinatesNP.type = INDI::IP_NUMBER;
    HorizontalCoordinatesNP.access = INDI::IP_RO;
    HorizontalCoordinatesNP.state = INDI::IPS_IDLE;
    HorizontalCoordinatesNP.perm = INDI::IP_RO;
    HorizontalCoordinatesNP.nnp = 2;
}

// Helper function to send a command and get a response
bool PiFinder::SendCommand(const char *cmd, char *response, int max_len)
{
    if (pifinder_fd < 0)
        return false;

    DEBUGF(INDI::Logger::DBG_COMMAND, "CMD <%s>", cmd);
    if (write(pifinder_fd, cmd, strlen(cmd)) < 0)
    {
        DEBUGF(INDI::Logger::DBG_ERROR, "Error writing to socket: %s", strerror(errno));
        return false;
    }

    // Wait a bit for the response
    usleep(50000);

    int bytes_read = read(pifinder_fd, response, max_len - 1);
    if (bytes_read > 0)
    {
        response[bytes_read] = '\0';
        DEBUGF(INDI::Logger::DBG_COMMAND, "RES <%s>", response);
    }
    else
    {
        response[0] = '\0';
        DEBUGF(INDI::Logger::DBG_ERROR, "Error reading from socket");
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
        DEBUGF(INDI::Logger::DBG_ERROR, "Error creating socket: %s", strerror(errno));
        return false;
    }

    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(4030);
    server_addr.sin_addr.s_addr = inet_addr("127.0.0.1");

    if (connect(pifinder_fd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0)
    {
        DEBUGF(INDI::Logger::DBG_ERROR, "Error connecting to PiFinder: %s", strerror(errno));
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
    ln_precess_equ(&jnow_coords, jd, LN_JULIAN_DATE_J2000);
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

    // Tell INDI this is a Telescope
    this->SetCapability(INDI::TELESCOPE_CAN_GOTO, true);
    this->SetCapability(INDI::TELESCOPE_CAN_SYNC, true);
    this->SetCapability(INDI::TELESCOPE_CAN_ABORT, false);
    this->SetCapability(INDI::TELESCOPE_HAS_ON_BOARD_CLOCK, false);
    this->SetCapability(INDI::TELESCOPE_HAS_GEOGRAPHIC_LOCATION, false);

    // We want to manage the connection ourselves
    this->SetCapability(INDI::CONNECTION_CAP, true);

    // Equatorial coordinates
    this->EquatorialEODNP.fill("EQUATORIAL_EOD_COORD", "RA/DE", "JNow", INDI::IP_RW, 0, 60);
    this->EquatorialEODN[0].fill("RA", "RA", "%02.0f:%02.0f:%04.1f", 0, 24, 0, 0);
    this->EquatorialEODN[1].fill("DEC", "Dec", "+%02.0f:%02.0f:%02.0f", -90, 90, 0, 0);
    
    // Add the properties to the driver
    this->defineNumber(&EquatorialEODNP);

    return true;
}

bool PiFinder::updateProperties()
{
    // Update properties defined in parent
    INDI::DefaultDevice::updateProperties();

    if (this->isConnected())
    {
        // We are connected, so we are ready to receive commands
        this->defineText(&HorizontalCoordinatesNP);
    }
    else
    {
        // We are not connected, so we cannot receive commands
        this->deleteProperty(HorizontalCoordinatesNP.name);
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
    // We check if the user is trying to connect or disconnect
    if (strcmp(name, "CONNECTION") == 0)
    {
        // The user is trying to connect or disconnect
        if (states[0].s == ISS_ON)
        {
            // The user is trying to connect
            if (Handshake())
            {
                // We are connected
                this->ConnectionS[0].s = INDI::ISS_ON;
                this->ConnectionS[1].s = INDI::ISS_OFF;
            }
            else
            {
                // We are not connected
                this->ConnectionS[0].s = INDI::ISS_OFF;
                this->ConnectionS[1].s = INDI::ISS_ON;
            }
        }
        else
        {
            // The user is trying to disconnect
            Close();
            this->ConnectionS[0].s = INDI::ISS_OFF;
            this->ConnectionS[1].s = INDI::ISS_ON;
        }
    }

    // We update the CONNECTION property
    this->ConnectionSP.s = INDI::IPS_OK;
    this->IDSetSwitch(&ConnectionSP, nullptr);
    return true;
}

bool PiFinder::ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n)
{
    // We check if the user is trying to set the horizontal coordinates
    if (strcmp(name, "HORIZONTAL_COORDINATES") == 0)
    {
        // The user is trying to set the horizontal coordinates
        // We parse the coordinates
        double alt, az;
        if (sscanf(texts[0], "%lf", &alt) == 1 && sscanf(texts[1], "%lf", &az) == 1)
        {
            // We set the coordinates
            this->HorizontalCoordinatesN[0].value = alt;
            this->HorizontalCoordinatesN[1].value = az;
            this->HorizontalCoordinatesNP.s = INDI::IPS_OK;
        }
        else
        {
            // We cannot parse the coordinates
            this->HorizontalCoordinatesNP.s = INDI::IPS_ALERT;
        }
    }

    // We update the HORIZONTAL_COORDINATES property
    this->IDSetText(&HorizontalCoordinatesNP, nullptr);
    return true;
}

bool PiFinder::ISNewNumber(const char *dev, const char *name, double *values, char *names[], int n)
{
    if (strcmp(name, "EQUATORIAL_EOD_COORD") == 0)
    {
        // The user is trying to set the equatorial coordinates (GoTo)
        double ra = values[0];
        double dec = values[1];

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
        
        this->EquatorialEODNP.s = INDI::IPS_BUSY;
        this->IDSetNumber(&EquatorialEODNP, nullptr);

        if (SendCommand(command, response, sizeof(response)) && response[0] == '1')
        {
            this->EquatorialEODNP.s = INDI::IPS_OK;
            this->EquatorialEODN[0].value = ra;
            this->EquatorialEODN[1].value = dec;
        }
        else
        {
            this->EquatorialEODNP.s = INDI::IPS_ALERT;
        }
        this->IDSetNumber(&EquatorialEODNP, nullptr);
        return true;
    }

    // We check if the user is trying to set the horizontal coordinates
    if (strcmp(name, "HORIZONTAL_COORDINATES") == 0)
    {
        // The user is trying to set the horizontal coordinates
        // We set the coordinates
        this->HorizontalCoordinatesN[0].value = values[0];
        this->HorizontalCoordinatesN[1].value = values[1];
        this->HorizontalCoordinatesNP.s = INDI::IPS_OK;
    }

    // We update the HORIZONTAL_COORDINATES property
    this->IDSetNumber(&HorizontalCoordinatesNP, nullptr);
    return true;
}

bool PiFinder::ISNewBLOB(const char *dev, const char *name, int sizes[], int blobsizes[], char *blobs[], char *formats[], char *names[], int n)
{
    // We call the parent method
    return INDI::DefaultDevice::ISNewBLOB(dev, name, sizes, blobsizes, blobs, formats, names, n);
}
