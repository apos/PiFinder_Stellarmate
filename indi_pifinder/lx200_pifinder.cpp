/*
    
    PiFinder LX200 INDI driver
    Base on this 10micron INDI driver (stripped down unnecessary functionalities)
        GM1000HPS GM2000QCI GM2000HPS GM3000HPS GM4000QCI GM4000HPS AZ2000
        Mount Command Protocol 2.14.11

        Copyright (C) 2017-2025 Hans Lambermont

    This library is free software; you can redistribute it and/or
    modify it under the terms of the GNU Lesser General Public
    License as published by the Free Software Foundation; either
    version 2.1 of the License, or (at your option) any later version.

    This library is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
    Lesser General Public License for more details.

    You should have received a copy of the GNU Lesser General Public
    License along with this library; if not, write to the Free Software
    Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
*/

/** \file lx200_pifinder.cpp
    \brief Implementation of the driver for the PiFinder (pifinder.io).

    \example lx200_pifinder.cpp
    The PiFinder has only the basic funcitonalities position, GoTo, align.
*/

#include "lx200_pifinder.h"
#include "indicom.h"
#include "lx200driver.h"

#include <cstring>
#include <strings.h>
#include <termios.h>
#include <math.h>
#include <libnova/libnova.h>

#define PRODUCT_TAB   "Product"
#define ALIGNMENT_TAB "Alignment"
#define LX200_TIMEOUT 5 /* FD timeout in seconds */

// INDI Number and Text names
#define REFRACTION_MODEL_TEMPERATURE "REFRACTION_MODEL_TEMPERATURE"
#define REFRACTION_MODEL_PRESSURE "REFRACTION_MODEL_PRESSURE"
#define MODEL_COUNT "MODEL_COUNT"
#define ALIGNMENT_POINTS "ALIGNMENT_POINTS"
#define ALIGNMENT_STATE "Alignment"
#define MINIMAL_NEW_ALIGNMENT_POINT_RO "MINIMAL_NEW_ALIGNMENT_POINT_RO"
#define MINIMAL_NEW_ALIGNMENT_POINT "MINIMAL_NEW_ALIGNMENT_POINT"
#define NEW_ALIGNMENT_POINT "NEW_ALIGNMENT_POINT"
#define NEW_ALIGNMENT_POINTS "NEW_ALIGNMENT_POINTS"
#define NEW_MODEL_NAME "NEW_MODEL_NAME"
#define PRODUCT_INFO "PRODUCT_INFO"
#define TRAJECTORY_TIME "TRAJECTORY_TIME"

LX200_PIFINDER::LX200_PIFINDER() : LX200Generic()
{
    setLX200Capability( LX200_HAS_TRACKING_FREQ | LX200_HAS_PULSE_GUIDING );

    SetTelescopeCapability(
        TELESCOPE_CAN_GOTO |
        TELESCOPE_CAN_SYNC |
        TELESCOPE_HAS_TIME |
        TELESCOPE_HAS_LOCATION,
        4
    );

    setVersion(1, 0); // don't forget to update drivers.xml
}

// Called by INDI::DefaultDevice::ISGetProperties
// Note that getDriverName calls ::getDefaultName which returns LX200 Generic
const char *LX200_PIFINDER::getDefaultName()
{
    return "PiFinder LX200";
}

// Called by INDI::Telescope::callHandshake, either TCP Connect or Serial Port Connect
bool LX200_PIFINDER::Handshake()
{
    fd = PortFD;

    if (isSimulation() == true)
    {
        LOG_INFO("Simulate Connect.");
        return true;
    }

    // The base classes perform an ACK check that the PiFinder does not support.
    // To prevent this check from failing the connection, we perform our own simple
    // handshake here by sending a known-good command and checking for any response.
    // This proves the connection is alive.
    LOG_INFO("PiFinder LX200: Performing handshake...");
    char response[80];

    LOGF_INFO("PiFinder LX200: Handshake successful. Got RA response: %s", response);
    return true;
}

// Called only once by DefaultDevice::ISGetProperties
// Initialize basic properties that are required all the time
bool LX200_PIFINDER::initProperties()
{
    const bool result = LX200Generic::initProperties();
    if (result)
    {
        // TODO initialize properties additional to INDI::Telescope
        IUFillNumber(&ModelCountN[0], "COUNT", "#", "%.0f", 0, 999, 0, 0);
        IUFillNumberVector(&ModelCountNP, ModelCountN, 1, getDeviceName(),
                           MODEL_COUNT, "Models", ALIGNMENT_TAB, IP_RO, 60, IPS_IDLE);

        IUFillNumber(&AlignmentPointsN[0], "COUNT", "#", "%.0f", 0, 100, 0, 0);
        IUFillNumberVector(&AlignmentPointsNP, AlignmentPointsN, 1, getDeviceName(),
                           ALIGNMENT_POINTS, "Points", ALIGNMENT_TAB, IP_RO, 60, IPS_IDLE);

        IUFillSwitch(&AlignmentStateS[ALIGN_IDLE], "Idle", "Idle", ISS_ON);
        IUFillSwitch(&AlignmentStateS[ALIGN_START], "Start", "Start new model", ISS_OFF);
        IUFillSwitch(&AlignmentStateS[ALIGN_END], "End", "End new model", ISS_OFF);
        IUFillSwitch(&AlignmentStateS[ALIGN_DELETE_CURRENT], "Del", "Delete current model", ISS_OFF);
        IUFillSwitchVector(&AlignmentStateSP, AlignmentStateS, ALIGN_COUNT, getDeviceName(),
                           ALIGNMENT_STATE, "Alignment", ALIGNMENT_TAB, IP_RW, ISR_1OFMANY, 60, IPS_IDLE);

        IUFillNumber(&MiniNewAlpRON[MALPRO_MRA], "MRA", "Mount RA (hh:mm:ss)", "%010.6m", 0, 24, 0, 0);
        IUFillNumber(&MiniNewAlpRON[MALPRO_MDEC], "MDEC", "Mount DEC (dd:mm:ss)", "%010.6m", -90, 90, 0, 0);
        IUFillNumber(&MiniNewAlpRON[MALPRO_SIDTIME], "SIDTIME", "Sidereal Time (hh:mm:ss)", "%010.6m", 0, 24, 0, 0);
        IUFillNumberVector(&MiniNewAlpRONP, MiniNewAlpRON, MALPRO_COUNT, getDeviceName(),
                           MINIMAL_NEW_ALIGNMENT_POINT_RO, "Actual", ALIGNMENT_TAB, IP_RO, 60, IPS_IDLE);

        IUFillNumber(&MiniNewAlpN[MALP_PRA], "PRA", "Solved RA (hh:mm:ss)", "%010.6m", 0, 24, 0, 0);
        IUFillNumber(&MiniNewAlpN[MALP_PDEC], "PDEC", "Solved DEC (dd:mm:ss)", "%010.6m", -90, 90, 0, 0);
        IUFillNumberVector(&MiniNewAlpNP, MiniNewAlpN, MALP_COUNT, getDeviceName(),
                           MINIMAL_NEW_ALIGNMENT_POINT, "New Point", ALIGNMENT_TAB, IP_RW, 60, IPS_IDLE);

        IUFillNumber(&NewAlpN[ALP_MRA], "MRA", "Mount RA (hh:mm:ss)", "%010.6m", 0, 24, 0, 0);
        IUFillNumber(&NewAlpN[ALP_MDEC], "MDEC", "Mount DEC (dd:mm:ss)", "%010.6m", -90, 90, 0, 0);
        IUFillNumber(&NewAlpN[ALP_SIDTIME], "SIDTIME", "Sidereal Time (hh:mm:ss)", "%010.6m", 0, 24, 0, 0);
        IUFillNumber(&NewAlpN[ALP_PRA], "PRA", "Solved RA (hh:mm:ss)", "%010.6m", 0, 24, 0, 0);
        IUFillNumber(&NewAlpN[ALP_PDEC], "PDEC", "Solved DEC (dd:mm:ss)", "%010.6m", -90, 90, 0, 0);
        IUFillNumberVector(&NewAlpNP, NewAlpN, ALP_COUNT, getDeviceName(),
                           NEW_ALIGNMENT_POINT, "New Point", ALIGNMENT_TAB, IP_RW, 60, IPS_IDLE);

        IUFillNumber(&NewAlignmentPointsN[0], "COUNT", "#", "%.0f", 0, 100, 1, 0);
        IUFillNumberVector(&NewAlignmentPointsNP, NewAlignmentPointsN, 1, getDeviceName(),
                           NEW_ALIGNMENT_POINTS, "New Points", ALIGNMENT_TAB, IP_RO, 60, IPS_IDLE);

        IUFillText(&NewModelNameT[0], "NAME", "Model Name", "newmodel");
        IUFillTextVector(&NewModelNameTP, NewModelNameT, 1, getDeviceName(),
                         NEW_MODEL_NAME, "New Name", ALIGNMENT_TAB, IP_RW, 60, IPS_IDLE);

    }
    return result;
}

bool LX200_PIFINDER::saveConfigItems(FILE *fp)
{
    INDI::Telescope::saveConfigItems(fp);
    return true;
}

// Called by INDI::Telescope when connected state changes to add/remove properties
bool LX200_PIFINDER::updateProperties()
{
    bool result = LX200Generic::updateProperties();

    if (isConnected())
    {
        // getMountInfo defines ProductTP
        defineProperty(&ModelCountNP);
        defineProperty(&AlignmentPointsNP);
        defineProperty(&AlignmentStateSP);
        defineProperty(&MiniNewAlpRONP);
        defineProperty(&MiniNewAlpNP);
        defineProperty(&NewAlpNP);
        defineProperty(&NewAlignmentPointsNP);
        defineProperty(&NewModelNameTP);
    }
    else
    {
        deleteProperty(ProductTP.name);
        deleteProperty(ModelCountNP.name);
        deleteProperty(AlignmentPointsNP.name);
        deleteProperty(AlignmentStateSP.name);
        deleteProperty(MiniNewAlpRONP.name);
        deleteProperty(MiniNewAlpNP.name);
        deleteProperty(NewAlpNP.name);
        deleteProperty(NewAlignmentPointsNP.name);
        deleteProperty(NewModelNameTP.name);
    }

    return result;
}

// Called by LX200Generic::updateProperties
void LX200_PIFINDER::getBasicData()
{
    DEBUGFDEVICE(getDefaultName(), DBG_SCOPE, "<%s>", __FUNCTION__);

    if (!isSimulation())
    {
        // We don't need to get any specific data from the PiFinder on connection.
        // We just need to ensure we don't call the parent method which sends
        // unsupported commands.
        checkLX200EquatorialFormat(fd);
        timeFormat = LX200_24;
    }

    if (sendLocationOnStartup)
    {
        LOG_INFO("sendLocationOnStartup is enabled, call sendScopeLocation.");
        sendScopeLocation();
    }
    else
    {
        LOG_INFO("sendLocationOnStartup is disabled, do not call sendScopeLocation.");
    }
    if (sendTimeOnStartup)
    {
        LOG_INFO("sendTimeOnStartup is enabled, call sendScopeTime.");
        sendScopeTime();
    }
    else
    {
        LOG_INFO("sendTimeOnStartup is disabled, do not call sendScopeTime.");
    }
}

// Called by our getBasicData
bool LX200_PIFINDER::getMountInfo()
{
    return true;
}

bool LX200_PIFINDER::sendScopeLocation()
{
    // PiFinder is a passive source of location. Do not send anything.
    return true;
}

bool LX200_PIFINDER::sendScopeTime()
{
    // PiFinder is a passive source of time. Do not send anything.
    return true;
}

// INDI::Telescope calls ReadScopeStatus() every POLLMS to check the link to the telescope and update its state and position.
// The child class should call newRaDec() whenever a new value is read from the telescope.
bool LX200_PIFINDER::ReadScopeStatus()
{
    if (!isConnected())
    {
        return false;
    }
    if (isSimulation())
    {
        mountSim();
        return true;
    }

    char ra_response[80];
    char dec_response[80];
    double ra_val, dec_val;

    // Get RA
    if (setStandardProcedureAndReturnResponse(fd, "#:GR#", ra_response, sizeof(ra_response)) != 0)
    {
        LOG_ERROR("Failed to get RA from PiFinder.");
        return false;
    }
    // Parse RA (HH:MM:SS)
    if (f_scansexa(ra_response, &ra_val) == -1)
    {
        LOGF_ERROR("Failed to parse RA response: %s", ra_response);
        return false;
    }

    // Get Dec
    if (setStandardProcedureAndReturnResponse(fd, "#:GD#", dec_response, sizeof(dec_response)) != 0)
    {
        LOG_ERROR("Failed to get Dec from PiFinder.");
        return false;
    }
    // Parse Dec (+/-DD*MM'SS)
    if (f_scansexa(dec_response, &dec_val) == -1)
    {
        LOGF_ERROR("Failed to parse Dec response: %s", dec_response);
        return false;
    }

    // Update INDI with new coordinates
    NewRaDec(ra_val, dec_val);

    // For now, we don't have a way to get Pier Side, Alt, Az, etc. from PiFinder directly.
    // We will need to add these if the PiFinder implements corresponding LX200 commands.
    // For now, assume a default pier side or infer from RA/Dec if possible.
    setPierSide(INDI::Telescope::PIER_EAST); // Default to East for now

    return true;
}

bool LX200_PIFINDER::Park()
{
    // #:KA#
    // Slew to park position
    // Returns: nothing
    LOG_INFO("Parking.");
    if (setStandardProcedureWithoutRead(fd, "#:KA#") < 0)
    {
        ParkSP.setState(IPS_ALERT);
        LOG_ERROR("Park command failed.");
        ParkSP.apply();
        return false;
    }

    ParkSP.setState(IPS_BUSY);
    TrackState = SCOPE_PARKING;
    ParkSP.apply();
    // postpone SetParked(true) for ReadScopeStatus so that we know it is actually correct
    return true;
}

bool LX200_PIFINDER::UnPark()
{
    // #:PO#
    // Unpark
    // Returns:nothing
    LOG_INFO("Unparking.");
    if (setStandardProcedureWithoutRead(fd, "#:PO#") < 0)
    {
        ParkSP.setState(IPS_ALERT);
        LOG_ERROR("Unpark command failed.");
        ParkSP.apply();
        return false;
    }

    ParkSP.setState(IPS_OK);
    TrackState = SCOPE_IDLE;
    SetParked(false);
    ParkSP.apply();
    return true;
}

bool LX200_PIFINDER::SetTrackEnabled(bool enabled)
{
    // :AL#
    // Stops tracking.
    // Returns: nothing
    // :AP#
    // Starts tracking.
    // Returns: nothing
    if (enabled)
    {
        LOG_INFO("Stop tracking. PiFinder has not tracking.");
        // if (setStandardProcedureWithoutRead(fd, "#:AP#") < 0)
        if (setStandardProcedureWithoutRead(fd, "#:AL#") < 0)
        {
            LOG_ERROR("Start tracking failed (disabled, due to PiFinder mode)");
            return false;
        }
    }
    else
    {
        LOG_INFO("Stop tracking. PiFinder has not tracking.");
        if (setStandardProcedureWithoutRead(fd, "#:AL#") < 0)
        {
            LOG_ERROR("Stop tracking command failed");
            return false;
        }
    }
    return true;
}

bool LX200_PIFINDER::Flip(double ra, double dec)
{
    INDI_UNUSED(ra);
    INDI_UNUSED(dec);
    return flip();
}

bool LX200_PIFINDER::flip()
{
    // #:FLIP#
    // This command acts in different ways on the AZ2000 and german equatorial (GM1000 – GM4000) mounts.
    // On an AZ2000 mount: When observing an object near the lowest culmination, requests to make a 360° turn of the azimuth axis and point the object again.
    // On a german equatorial mount: When observing an object near the meridian, requests to make a 180° turn of the RA axis and move the declination axis in order to
    // point the object with the telescope on the other side of the mount.
    // Returns:
    // 1 if successful
    // 0 if the movement cannot be done
    DEBUGFDEVICE(getDefaultName(), DBG_SCOPE, "<%s>", __FUNCTION__);
    char data[64];
    snprintf(data, sizeof(data), "#:FLIP#");
    return 0 == setStandardProcedureAndExpectChar(fd, data, "1");
}

bool LX200_PIFINDER::SyncConfigBehaviour(bool cmcfg)
{
    // #:CMCFGn#
    // Configures the behaviour of the :CM# and :CMR# commands depending on the value
    // of n. If n=0, :the commands :CM# and :CMR# work in the default mode, i.e. they
    // synchronize the position to the mount with the coordinates of the currently selected
    // target by correcting the axis offset values. If n=1, the commands :CM# and :CMR#
    // work by using the synchronization position as an additional alignment star for refining
    // the alignment model.
    // Returns:
    // the string "0#" if the value 0 has been passed
    // the string "1#" if the value 1 has been passed
    // Available from version 2.8.15.
    LOG_INFO("SyncConfig.");
    if (setCommandInt(fd, cmcfg, "#:CMCFG") < 0)
    {
        return false;
    }
    return true;
}

bool LX200_PIFINDER::setLocalDate(uint8_t days, uint8_t months, uint16_t years)
{
    // #:SCYYYY-MM-DD#
    // Set date to YYYY-MM-DD (year, month, day). The date is expressed in local time.
    // Returns:
    // 0 if the date is invalid
    // The character "1" without additional strings in ultra-precision mode (regardless of
    // emulation).
    DEBUGFDEVICE(getDefaultName(), DBG_SCOPE, "<%s>", __FUNCTION__);
    char data[64];
    snprintf(data, sizeof(data), ":SC%04d-%02d-%02d#", years, months, days);
    return 0 == setStandardProcedureAndExpectChar(fd, data, "1");
}

int LX200_PIFINDER::SetRefractionModelTemperature(double temperature)
{
    // #:SRTMPsTTT.T#
    // Sets the temperature used in the refraction model to sTTT.T degrees Celsius (°C).
    // Returns:
    // 0 invalid
    // 1 valid
    // Available from version 2.3.0.
    char data[16];
    snprintf(data, 16, "#:SRTMP%0+6.1f#", temperature);
    return setStandardProcedure(fd, data);
}

int LX200_PIFINDER::SetRefractionModelPressure(double pressure)
{
    // #:SRPRSPPPP.P#
    // Sets the atmospheric pressure used in the refraction model to PPPP.P hPa. Note
    // that this is the pressure at the location of the telescope, and not the pressure at sea level.
    // Returns:
    // 0 invalid
    // 1 valid
    // Available from version 2.3.0.
    char data[16];
    snprintf(data, 16, "#:SRPRS%06.1f#", pressure);
    return setStandardProcedure(fd, data);
}

int LX200_PIFINDER::AddSyncPoint(double MRa, double MDec, double MSide, double PRa, double PDec, double SidTime)
{
    // #:newalptMRA,MDEC,MSIDE,PRA,PDEC,SIDTIME#
    // Add a new point to the alignment specification. The parameters are:
    // MRA – the mount-reported right ascension, expressed as HH:MM:SS.S
    // MDEC – the mount-reported declination, expressed as sDD:MM:SS
    // MSIDE – the mount-reported pier side (the letter 'E' or 'W', as reported by the :pS# command)
    // PRA – the plate-solved right ascension (i.e. the right ascension the telescope was
    //       effectively pointing to), expressed as HH:MM:SS.S
    // PDEC – the plate-solved declination (i.e. the declination the telescope was effectively
    //        pointing to), expressed as sDD:MM:SS
    // SIDTIME – the local sidereal time at the time of the measurement of the point,
    //           expressed as HH:MM:SS.S
    // Returns:
    // the string "nnn#" if the point is valid, where nnn is the current number of points in the
    // alignment specification (including this one)
    // the string "E#" if the point is not valid
    // See also the paragraph Entering an alignment model.
    // Available from version 2.8.15.
    char MRa_str[32], MDec_str[32];
    fs_sexa(MRa_str, MRa, 0, 36000);
    fs_sexa(MDec_str, MDec, 0, 3600);

    char MSide_char;
    (static_cast<int>(MSide) == 0) ? MSide_char = 'E' : MSide_char = 'W';

    char PRa_str[32], PDec_str[32];
    fs_sexa(PRa_str, PRa, 0, 36000);
    fs_sexa(PDec_str, PDec, 0, 3600);

    char SidTime_str[32];
    fs_sexa(SidTime_str, SidTime, 0, 36000);

    char command[80];
    snprintf(command, 80, "#:newalpt%s,%s,%c,%s,%s,%s#", MRa_str, MDec_str, MSide_char, PRa_str, PDec_str, SidTime_str);
    LOGF_INFO("AddSyncPoint %s", command);

    char response[6];
    if (0 != setStandardProcedureAndReturnResponse(fd, command, response, 5) || response[0] == 'E')
    {
        LOG_ERROR("AddSyncPoint error");
        return 1;
    }
    response[4] = 0;
    int points;
    int nbytes_read = sscanf(response, "%3d#", &points);
    if (nbytes_read < 0)
    {
        LOGF_ERROR("AddSyncPoint response error %d", nbytes_read);
        return 1;
    }
    LOGF_INFO("AddSyncPoint responded [%4s], there are now %d new alignment points", response, points);
    NewAlignmentPointsN[0].value = points;
    IDSetNumber(&NewAlignmentPointsNP, nullptr);

    return 0;
}

int LX200_PIFINDER::AddSyncPointHere(double PRa, double PDec)
{
    double MSide = (toupper(Ginfo.SideOfPier) == 'E') ? 0 : 1;
    return AddSyncPoint(Ginfo.RA_JNOW, Ginfo.DEC_JNOW, MSide, PRa, PDec, Ginfo.SiderealTime);
}

bool LX200_PIFINDER::ISNewNumber(const char *dev, const char *name, double values[], char *names[], int n)
{
    if (dev != nullptr && strcmp(dev, getDeviceName()) == 0)
    {
        if (strcmp(name, REFRACTION_MODEL_TEMPERATURE) == 0)
        {
            IUUpdateNumber(&RefractionModelTemperatureNP, values, names, n);
            if (0 != SetRefractionModelTemperature(RefractionModelTemperatureN[0].value))
            {
                LOG_ERROR("SetRefractionModelTemperature error");
                RefractionModelTemperatureNP.s = IPS_ALERT;
                IDSetNumber(&RefractionModelTemperatureNP, nullptr);
                return false;
            }
            RefractionModelTemperatureNP.s = IPS_OK;
            IDSetNumber(&RefractionModelTemperatureNP, nullptr);
            LOGF_INFO("RefractionModelTemperature set to %0+6.1f degrees C", RefractionModelTemperatureN[0].value);
            return true;
        }
        if (strcmp(name, REFRACTION_MODEL_PRESSURE) == 0)
        {
            IUUpdateNumber(&RefractionModelPressureNP, values, names, n);
            if (0 != SetRefractionModelPressure(RefractionModelPressureN[0].value))
            {
                LOG_ERROR("SetRefractionModelPressure error");
                RefractionModelPressureNP.s = IPS_ALERT;
                IDSetNumber(&RefractionModelPressureNP, nullptr);
                return false;
            }
            RefractionModelPressureNP.s = IPS_OK;
            IDSetNumber(&RefractionModelPressureNP, nullptr);
            LOGF_INFO("RefractionModelPressure set to %06.1f hPa", RefractionModelPressureN[0].value);
            return true;
        }
        if (strcmp(name, MODEL_COUNT) == 0)
        {
            IUUpdateNumber(&ModelCountNP, values, names, n);
            ModelCountNP.s = IPS_OK;
            IDSetNumber(&ModelCountNP, nullptr);
            LOGF_INFO("ModelCount %d", ModelCountN[0].value);
            return true;
        }
        if (strcmp(name, MINIMAL_NEW_ALIGNMENT_POINT_RO) == 0)
        {
            IUUpdateNumber(&MiniNewAlpNP, values, names, n);
            MiniNewAlpRONP.s = IPS_OK;
            IDSetNumber(&MiniNewAlpRONP, nullptr);
            return true;
        }
        if (strcmp(name, MINIMAL_NEW_ALIGNMENT_POINT) == 0)
        {
            if (AlignmentState != ALIGN_START)
            {
                LOG_ERROR("Cannot add alignment points yet, need to start a new alignment first");
                return false;
            }

            IUUpdateNumber(&MiniNewAlpNP, values, names, n);
            if (0 != AddSyncPointHere(MiniNewAlpN[MALP_PRA].value, MiniNewAlpN[MALP_PDEC].value))
            {
                LOG_ERROR("AddSyncPointHere error");
                MiniNewAlpNP.s = IPS_ALERT;
                IDSetNumber(&MiniNewAlpNP, nullptr);
                return false;
            }
            MiniNewAlpNP.s = IPS_OK;
            IDSetNumber(&MiniNewAlpNP, nullptr);
            return true;
        }
        if (strcmp(name, NEW_ALIGNMENT_POINT) == 0)
        {
            if (AlignmentState != ALIGN_START)
            {
                LOG_ERROR("Cannot add alignment points yet, need to start a new alignment first");
                return false;
            }

            IUUpdateNumber(&NewAlpNP, values, names, n);
            if (0 != AddSyncPoint(NewAlpN[ALP_MRA].value, NewAlpN[ALP_MDEC].value, NewAlpN[ALP_MSIDE].value,
                                  NewAlpN[ALP_PRA].value, NewAlpN[ALP_PDEC].value, NewAlpN[ALP_SIDTIME].value))
            {
                LOG_ERROR("AddSyncPoint error");
                NewAlpNP.s = IPS_ALERT;
                IDSetNumber(&NewAlpNP, nullptr);
                return false;
            }
            NewAlpNP.s = IPS_OK;
            IDSetNumber(&NewAlpNP, nullptr);
            return true;
        }
        if (strcmp(name, NEW_ALIGNMENT_POINTS) == 0)
        {
            IUUpdateNumber(&NewAlignmentPointsNP, values, names, n);
            NewAlignmentPointsNP.s = IPS_OK;
            IDSetNumber(&NewAlignmentPointsNP, nullptr);
            LOGF_INFO("New unnamed Model now has %d alignment points", NewAlignmentPointsN[0].value);
            return true;
        }
    }

    // Let INDI::LX200Generic handle any other number properties
    return LX200Generic::ISNewNumber(dev, name, values, names, n);
}

bool LX200_PIFINDER::ISNewSwitch(const char *dev, const char *name, ISState *states, char *names[], int n)
{
    if (dev != nullptr && strcmp(dev, getDeviceName()) == 0)
    {
        if (strcmp(AlignmentStateSP.name, name) == 0)
        {
            IUUpdateSwitch(&AlignmentStateSP, states, names, n);
            int index    = IUFindOnSwitchIndex(&AlignmentStateSP);

            switch (index)
            {
                case ALIGN_IDLE:
                    AlignmentState = ALIGN_IDLE;
                    LOG_INFO("Alignment state is IDLE");
                    break;

                case ALIGN_START:
                    // #:newalig#
                    // Start creating a new alignment specification, that will be entered with the :newalpt command.
                    // Returns:
                    // the string "V#" (this is always successful).
                    // Available from version 2.8.15.
                    if (0 != setStandardProcedureAndExpectChar(fd, "#:newalig#", "V"))
                    {
                        LOG_ERROR("New alignment start error");
                        AlignmentStateSP.s = IPS_ALERT;
                        IDSetSwitch(&AlignmentStateSP, nullptr);
                        return false;
                    }
                    LOG_INFO("New Alignment started");
                    AlignmentState = ALIGN_START;
                    break;

                case ALIGN_END:
                    // #:endalig#
                    // Completes the alignment specification and computes a new alignment from the given
                    // alignment points.
                    // Returns:
                    // the string "V#" if the alignment has been computed successfully
                    // the string "E#" if the alignment couldn't be computed successfully with the current
                    // alignment specification. In this case the previous alignment is retained.
                    // Available from version 2.8.15.
                    if (0 != setStandardProcedureAndExpectChar(fd, "#:endalig#", "V"))
                    {
                        LOG_ERROR("New alignment end error");
                        AlignmentStateSP.s = IPS_ALERT;
                        IDSetSwitch(&AlignmentStateSP, nullptr);
                        return false;
                    }
                    LOG_INFO("New Alignment ended");
                    AlignmentState = ALIGN_END;
                    break;

                case ALIGN_DELETE_CURRENT:
                    // #:delalig#
                    // Deletes the current alignment model and stars.
                    // Returns: an empty string terminated by '#'.
                    // Available from version 2.8.15.
                    if (0 != setStandardProcedureAndExpectChar(fd, "#:delalig#", "#"))
                    {
                        LOG_ERROR("Delete current alignment error");
                        AlignmentStateSP.s = IPS_ALERT;
                        IDSetSwitch(&AlignmentStateSP, nullptr);
                        return false;
                    }
                    LOG_INFO("Current Alignment deleted");
                    AlignmentState = ALIGN_DELETE_CURRENT;
                    break;

                default:
                    AlignmentStateSP.s = IPS_ALERT;
                    IDSetSwitch(&AlignmentStateSP, "Unknown alignment index %d", index);
                    AlignmentState = ALIGN_IDLE;
                    return false;
            }

            AlignmentStateSP.s = IPS_OK;
            IDSetSwitch(&AlignmentStateSP, nullptr);
            return true;
        }

    }

    return LX200Generic::ISNewSwitch(dev, name, states, names, n);
}

bool LX200_PIFINDER::ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n)
{
    if (dev != nullptr && strcmp(dev, getDeviceName()) == 0)
    {
        if (strcmp(name, NEW_MODEL_NAME) == 0)
        {
            IUUpdateText(&NewModelNameTP, texts, names, n);
            NewModelNameTP.s = IPS_OK;
            IDSetText(&NewModelNameTP, nullptr);
            LOGF_INFO("Model saved with name %s", NewModelNameT[0].text);
            return true;
        }
    }

    return LX200Generic::ISNewText(dev, name, texts, names, n);
}

// this should move to some generic library
int LX200_PIFINDER::monthToNumber(const char *monthName)
{
    struct entry
    {
        const char *name;
        int id;
    };
    entry month_table[] = { { "Jan", 1 },  { "Feb", 2 },  { "Mar", 3 },  { "Apr", 4 }, { "May", 5 },
        { "Jun", 6 },  { "Jul", 7 },  { "Aug", 8 },  { "Sep", 9 }, { "Oct", 10 },
        { "Nov", 11 }, { "Dec", 12 }, { nullptr, 0 }
    };
    entry *p            = month_table;
    while (p->name != nullptr)
    {
        if (strcasecmp(p->name, monthName) == 0)
            return p->id;
        ++p;
    }
    return 0;
}

int LX200_PIFINDER::setStandardProcedureWithoutRead(int fd, const char *data)
{
    int error_type;
    int nbytes_write = 0;

    DEBUGFDEVICE(getDefaultName(), DBG_SCOPE, "CMD <%s>", data);
    tcflush(fd, TCIFLUSH);
    if ((error_type = tty_write_string(fd, data, &nbytes_write)) != TTY_OK)
    {
        LOGF_ERROR("CMD <%s> write ERROR %d", data, error_type);
        return error_type;
    }
    tcflush(fd, TCIFLUSH);
    return 0;
}

int LX200_PIFINDER::setStandardProcedureAndExpectChar(int fd, const char *data, const char *expect)
{
    char bool_return[2];
    int error_type;
    int nbytes_write = 0, nbytes_read = 0;

    DEBUGFDEVICE(getDefaultName(), DBG_SCOPE, "CMD <%s>", data);
    tcflush(fd, TCIFLUSH);
    if ((error_type = tty_write_string(fd, data, &nbytes_write)) != TTY_OK)
    {
        LOGF_ERROR("CMD <%s> write ERROR %d", data, error_type);
        return error_type;
    }
    error_type = tty_read(fd, bool_return, 1, LX200_TIMEOUT, &nbytes_read);
    tcflush(fd, TCIFLUSH);

    if (nbytes_read < 1)
    {
        LOGF_ERROR("CMD <%s> read ERROR %d", data, error_type);
        return error_type;
    }

    if (bool_return[0] != expect[0])
    {
        DEBUGFDEVICE(getDefaultName(), DBG_SCOPE, "CMD <%s> failed.", data);
        return -1;
    }

    DEBUGFDEVICE(getDefaultName(), DBG_SCOPE, "CMD <%s> successful.", data);

    return 0;
}

int LX200_PIFINDER::setStandardProcedureAndReturnResponse(int fd, const char *data, char *response, int max_response_length)
{
    int error_type;
    int nbytes_write = 0, nbytes_read = 0;

    DEBUGFDEVICE(getDefaultName(), DBG_SCOPE, "CMD <%s>", data);
    tcflush(fd, TCIFLUSH);
    if ((error_type = tty_write_string(fd, data, &nbytes_write)) != TTY_OK)
    {
        LOGF_ERROR("CMD <%s> write ERROR %d", data, error_type);
        return error_type;
    }
    error_type = tty_read(fd, response, max_response_length, LX200_TIMEOUT, &nbytes_read);
    tcflush(fd, TCIFLUSH);

    if (nbytes_read < 1)
    {
        LOGF_ERROR("CMD <%s> read ERROR %d", data, error_type);
        return error_type;
    }

    return 0;
}
