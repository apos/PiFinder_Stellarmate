/*

    PiFinder LX200 INDI driver

    PiFinder has no motorized mount of its own: it is a plate-solving push-to
    aid. This driver reports PiFinder's solved position and, on Goto(), reuses
    PiFinder's existing SkySafari "push-to" mechanism (:Sr#/:Sd#, already
    implemented in PiFinder's pos_server.py) to register a target in the
    PiFinder UI - that direction needs no PiFinder-side change. The reverse
    direction (an on-device push-to selection, PiFinder's own catalog/menu)
    does need a small PiFinder-side patch (see PiFinder_Stellarmate#171 and
    diffs/object_details_py.diff) - pollCurrentTarget() below polls its
    /api/current_target and republishes via TargetNP, same as any Goto().

    Originally based on a 10micron INDI driver (GM1000HPS GM2000QCI GM2000HPS
    GM3000HPS GM4000QCI GM4000HPS AZ2000, Mount Command Protocol 2.14.11),
    Copyright (C) 2017-2025 Hans Lambermont, since stripped down to the
    position + push-to-goto functionality PiFinder actually has: no park, no
    flip, no tracking control, no refraction model, no custom alignment
    protocol.

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
    The PiFinder has only the basic functionalities position and GoTo (push-to).
*/

#include "lx200_pifinder.h"
#include "indicom.h"
#include "lx200driver.h"
#include "connectionplugins/connectiontcp.h"

#include <cmath>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <memory>
#include <optional>
#include <string>
#include <termios.h>
#include <libnova/libnova.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>

#include <curl/curl.h>
#include <nlohmann/json.hpp>

namespace
{
// Same pattern as PiFinder Mount Bridge's own HTTP GET helper
// (pifinder_mount_bridge.cpp) - single-threaded INDI driver (TimerHit/
// ReadScopeStatus callback style), no explicit curl_global_init() needed.
size_t appendToString(char *ptr, size_t size, size_t nmemb, void *userdata)
{
    static_cast<std::string *>(userdata)->append(ptr, size * nmemb);
    return size * nmemb;
}

// Fetches PiFinder's own /api/current_target. RA/Dec come back J2000 (see
// that endpoint's own docstring) - precession to JNow happens in
// pollCurrentTarget() below, not here. Returns false on any request/parse
// failure or if no target is currently selected.
bool httpGetCurrentTarget(const std::string &url, double &raJ2000, double &decJ2000, std::string &name)
{
    CURL *curl = curl_easy_init();
    if (curl == nullptr)
        return false;

    std::string body;
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, appendToString);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &body);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, 1500L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);

    const CURLcode res = curl_easy_perform(curl);
    long httpCode = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpCode);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK || httpCode != 200)
        return false;

    try
    {
        const auto parsed = nlohmann::json::parse(body);
        const auto &target = parsed.at("target");
        if (target.is_null())
            return false;
        raJ2000 = target.at("ra").get<double>();
        decJ2000 = target.at("dec").get<double>();
        name = target.value("name", std::string());
        return true;
    }
    catch (const nlohmann::json::exception &)
    {
        return false;
    }
}

// Fetches PiFinder's own /api/hardware_status (see diffs/server_py.diff) -
// Camera/IMU presence, system load and Mount Type/Screen Direction, all in
// one request. camera_present/imu_present come back as JSON true/false/null
// (null = "the check itself couldn't run", distinct from a confirmed
// false) - std::optional<bool> carries that tri-state through cleanly.
// Returns false on any request/parse failure (all out-params left
// untouched, matching this file's other httpGet* helpers).
struct PiFinderHardwareStatus
{
    std::optional<bool> cameraPresent;
    std::optional<bool> imuPresent;
    double load1 = 0, load5 = 0, load15 = 0, cpuCount = 0, percent = 0;
    double tempC = std::numeric_limits<double>::quiet_NaN();
    std::string mountType;
    std::string screenDirection;
};

std::optional<PiFinderHardwareStatus> httpGetPiFinderHardwareStatus(const std::string &url)
{
    CURL *curl = curl_easy_init();
    if (curl == nullptr)
        return std::nullopt;

    std::string body;
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, appendToString);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &body);
    // Generous compared to this file's other 1500ms HTTP calls: the
    // underlying check on PiFinder's side (rpicam-hello --list-cameras) can
    // itself take several seconds under load (see _camera_hardware_present()'s
    // own comment in gui_installer/server.py) - but still bounded, and this
    // call only ever runs from pollHardwareStatus()'s own rate-limited gate,
    // never on every fast ReadScopeStatus() tick.
    curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, 4000L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);

    const CURLcode res = curl_easy_perform(curl);
    long httpCode = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpCode);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK || httpCode != 200)
        return std::nullopt;

    try
    {
        const auto parsed = nlohmann::json::parse(body);
        PiFinderHardwareStatus status;
        const auto &camera = parsed.at("camera_present");
        status.cameraPresent = camera.is_null() ? std::optional<bool>() : std::optional<bool>(camera.get<bool>());
        const auto &imu = parsed.at("imu_present");
        status.imuPresent = imu.is_null() ? std::optional<bool>() : std::optional<bool>(imu.get<bool>());
        status.load1 = parsed.value("load1", 0.0);
        status.load5 = parsed.value("load5", 0.0);
        status.load15 = parsed.value("load15", 0.0);
        status.cpuCount = parsed.value("cpu_count", 0.0);
        status.percent = parsed.value("percent", 0.0);
        const auto &temp = parsed.at("temp_c");
        status.tempC = temp.is_null() ? std::numeric_limits<double>::quiet_NaN() : temp.get<double>();
        status.mountType = parsed.value("mount_type", std::string());
        status.screenDirection = parsed.value("screen_direction", std::string());
        return status;
    }
    catch (const nlohmann::json::exception &)
    {
        return std::nullopt;
    }
}
}

// See #139's investigation: pos_server.py can take several seconds to
// answer under CPU load without the connection actually being dead. Retry
// a handful of times with this much shorter per-attempt timeout instead of
// one long LX200_TIMEOUT-second block per read (see readWithRetry()).
static constexpr int LX200_READ_ATTEMPT_TIMEOUT = 2;
static constexpr int LX200_READ_MAX_ATTEMPTS = 3;

// Standalone driver executable: no multi-driver Loader/fat-binary needed.
// Links directly against the system's libindilx200/libindidriver.
static std::unique_ptr<LX200_PIFINDER> pifinder_driver(new LX200_PIFINDER());

LX200_PIFINDER::LX200_PIFINDER() : LX200Telescope()
{
    setLX200Capability( LX200_HAS_TRACKING_FREQ | LX200_HAS_PULSE_GUIDING );

    SetTelescopeCapability(
        TELESCOPE_CAN_GOTO |
        TELESCOPE_CAN_ABORT |
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

    // #139-adjacent: enable TCP keepalive so a truly-dead connection (peer
    // process gone without a clean close - the original #118 symptom) gets
    // detected by the OS itself within ~11s, instead of relying purely on
    // read()/write() to eventually notice. Tuned short deliberately - this
    // is always a loopback connection to pos_server.py on the same Pi, not
    // a real network link, so aggressive probing costs nothing.
    int keepalive = 1;
    setsockopt(fd, SOL_SOCKET, SO_KEEPALIVE, &keepalive, sizeof(keepalive));
    int keepidle = 5;   // start probing after 5s idle
    int keepintvl = 3;  // probe every 3s
    int keepcnt = 3;    // give up (fail reads/writes) after 3 missed probes
    setsockopt(fd, IPPROTO_TCP, TCP_KEEPIDLE, &keepidle, sizeof(keepidle));
    setsockopt(fd, IPPROTO_TCP, TCP_KEEPINTVL, &keepintvl, sizeof(keepintvl));
    setsockopt(fd, IPPROTO_TCP, TCP_KEEPCNT, &keepcnt, sizeof(keepcnt));

    // The base classes perform an ACK check that PiFinder does not support.
    // Since PiFinder always answers plain reads like :GR#/:GD# below, we
    // don't need a dedicated handshake command - just accept the connection.
    LOG_INFO("PiFinder LX200: connection established.");
    return true;
}

// Called only once by DefaultDevice::ISGetProperties
// Initialize basic properties that are required all the time
bool LX200_PIFINDER::initProperties()
{
    const bool result = LX200Telescope::initProperties();
    if (result)
    {
        // Override the mount type property to make it writable, like the simulator.
        // This is crucial for clients like SkySafari which attempt to set this property on connection.
        MountTypeSP.fill(getDeviceName(), "TELESCOPE_MOUNT_TYPE", "Mount Type", MOTION_TAB, IP_RW, ISR_1OFMANY, 60, IPS_IDLE);

        // See the header's own comment on why these four exist. "yes"/"no"/
        // "unknown" strings (not a switch) so the tri-state - true/false/
        // "the check itself couldn't run" - is representable without
        // inventing a third switch state.
        IUFillText(&HardwarePresenceT[0], "CAMERA_PRESENT", "Camera present", "unknown");
        IUFillText(&HardwarePresenceT[1], "IMU_PRESENT", "IMU present", "unknown");
        IUFillTextVector(&HardwarePresenceTP, HardwarePresenceT, 2, getDeviceName(), "HARDWARE_PRESENCE",
                          "Hardware presence", "PiFinder Status", IP_RO, 60, IPS_IDLE);

        IUFillNumber(&SystemLoadN[0], "LOAD1", "Load avg (1 min)", "%.2f", 0, 1000, 0, 0);
        IUFillNumber(&SystemLoadN[1], "LOAD5", "Load avg (5 min)", "%.2f", 0, 1000, 0, 0);
        IUFillNumber(&SystemLoadN[2], "LOAD15", "Load avg (15 min)", "%.2f", 0, 1000, 0, 0);
        IUFillNumber(&SystemLoadN[3], "CPU_COUNT", "CPU count", "%.0f", 0, 256, 0, 0);
        IUFillNumber(&SystemLoadN[4], "PERCENT", "Load (% of available CPU)", "%.0f", 0, 10000, 0, 0);
        IUFillNumber(&SystemLoadN[5], "TEMP_C", "SoC temperature (C)", "%.1f", -50, 150, 0, 0);
        IUFillNumberVector(&SystemLoadNP, SystemLoadN, 6, getDeviceName(), "PIFINDER_SYSTEM_LOAD",
                            "System load", "PiFinder Status", IP_RO, 60, IPS_IDLE);

        // Same property name/shape as PiFinder Mount Bridge's own
        // PIFINDER_ORIENTATION (pifinder_mount_bridge.cpp) - same concept,
        // different device. Mount Bridge's copy only exists while Mount
        // Bridge itself is connected (always co-located with PiFinder); this
        // one exists whenever PiFinder LX200 is connected, including a
        // remote Control Host with no Mount Bridge running at all.
        IUFillText(&PiFinderOrientationT[0], "MOUNT_TYPE", "Mount Type", "");
        IUFillText(&PiFinderOrientationT[1], "SCREEN_DIRECTION", "Screen Direction", "");
        IUFillTextVector(&PiFinderOrientationTP, PiFinderOrientationT, 2, getDeviceName(), "PIFINDER_ORIENTATION",
                          "PiFinder orientation", "PiFinder Status", IP_RO, 60, IPS_IDLE);

        // IP_RW - see the header's own comment. Values are set externally
        // (the Control Center) via ISNewText, this driver only stores and
        // republishes them.
        IUFillText(&PiFinderModeT[0], "MODE", "Mode (fake/real/none)", "");
        IUFillText(&PiFinderModeT[1], "TRANSITIONING", "Mode switch in progress", "");
        IUFillText(&PiFinderModeT[2], "TARGET", "Mode switch target", "");
        IUFillText(&PiFinderModeT[3], "REAL_SERVICE_STATE", "Real service systemd state", "");
        IUFillText(&PiFinderModeT[4], "ROLE_CHOICE", "PiFinder role (host/client)", "");
        IUFillTextVector(&PiFinderModeTP, PiFinderModeT, 5, getDeviceName(), "PIFINDER_MODE",
                          "Control Center mode", "PiFinder Status", IP_RW, 60, IPS_IDLE);
    }
    return result;
}

bool LX200_PIFINDER::updateProperties()
{
    const bool result = LX200Telescope::updateProperties();

    if (isConnected())
    {
        defineProperty(&HardwarePresenceTP);
        defineProperty(&SystemLoadNP);
        defineProperty(&PiFinderOrientationTP);
        defineProperty(&PiFinderModeTP);
    }
    else
    {
        deleteProperty(HardwarePresenceTP.name);
        deleteProperty(SystemLoadNP.name);
        deleteProperty(PiFinderOrientationTP.name);
        deleteProperty(PiFinderModeTP.name);
    }

    return result;
}

bool LX200_PIFINDER::ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n)
{
    if (dev != nullptr && strcmp(dev, getDeviceName()) == 0 && strcmp(name, PiFinderModeTP.name) == 0)
    {
        IUUpdateText(&PiFinderModeTP, texts, names, n);
        PiFinderModeTP.s = IPS_OK;
        IDSetText(&PiFinderModeTP, nullptr);
        return true;
    }
    return LX200Telescope::ISNewText(dev, name, texts, names, n);
}

// Called by LX200Telescope::updateProperties
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

bool LX200_PIFINDER::updateLocation(double latitude, double longitude, double elevation)
{
    LOGF_INFO("updateLocation called, ignoring. Lat: %f, Lon: %f, Elev: %f", latitude, longitude, elevation);
    return true;
}

bool LX200_PIFINDER::updateTime(ln_date *utc, double utc_offset)
{
    (void)utc; // Suppress unused parameter warning
    LOGF_INFO("updateTime called, ignoring. UTC Offset: %f", utc_offset);
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
    if (readWithRetry("#:GR#", ra_response, sizeof(ra_response)) != 0)
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
    if (readWithRetry("#:GD#", dec_response, sizeof(dec_response)) != 0)
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

    pollCurrentTarget();
    pollHardwareStatus();

    return true;
}

// Rate-limited to once per 20s (matches the existing GUI's own
// refreshHardwareStatusAndDependents() cadence for these same facts) -
// see the header's own comment on why this can't run on every fast
// ReadScopeStatus() tick. Uses tcpConnection->host() (the currently
// configured device address - works whether this connects to a local or a
// remote PiFinder) same as pollCurrentTarget() should but currently
// doesn't (pre-existing, unrelated gap - out of scope here).
void LX200_PIFINDER::pollHardwareStatus()
{
    static constexpr int HARDWARE_STATUS_POLL_INTERVAL_SEC = 20;
    const time_t now = time(nullptr);
    if (m_lastHardwareStatusPoll != 0 && difftime(now, m_lastHardwareStatusPoll) < HARDWARE_STATUS_POLL_INTERVAL_SEC)
        return;
    m_lastHardwareStatusPoll = now;

    const char *host = (tcpConnection != nullptr) ? tcpConnection->host() : "127.0.0.1";

    auto status = httpGetPiFinderHardwareStatus("http://" + std::string(host) + "/api/hardware_status");
    if (!status.has_value())
        status = httpGetPiFinderHardwareStatus("http://" + std::string(host) + ":8080/api/hardware_status");
    if (!status.has_value())
    {
        HardwarePresenceTP.s = IPS_ALERT;
        IDSetText(&HardwarePresenceTP, nullptr);
        return;
    }

    auto presenceLabel = [](const std::optional<bool> &v) { return !v.has_value() ? "unknown" : (*v ? "yes" : "no"); };
    IUSaveText(&HardwarePresenceT[0], presenceLabel(status->cameraPresent));
    IUSaveText(&HardwarePresenceT[1], presenceLabel(status->imuPresent));
    HardwarePresenceTP.s = IPS_OK;
    IDSetText(&HardwarePresenceTP, nullptr);

    SystemLoadN[0].value = status->load1;
    SystemLoadN[1].value = status->load5;
    SystemLoadN[2].value = status->load15;
    SystemLoadN[3].value = status->cpuCount;
    SystemLoadN[4].value = status->percent;
    SystemLoadN[5].value = status->tempC;
    SystemLoadNP.s = IPS_OK;
    IDSetNumber(&SystemLoadNP, nullptr);

    IUSaveText(&PiFinderOrientationT[0], status->mountType.c_str());
    IUSaveText(&PiFinderOrientationT[1], status->screenDirection.c_str());
    PiFinderOrientationTP.s = IPS_OK;
    IDSetText(&PiFinderOrientationTP, nullptr);
}

void LX200_PIFINDER::pollCurrentTarget()
{
    double raJ2000, decJ2000;
    std::string name;
    const bool ok = httpGetCurrentTarget("http://127.0.0.1/api/current_target", raJ2000, decJ2000, name) ||
                    httpGetCurrentTarget("http://127.0.0.1:8080/api/current_target", raJ2000, decJ2000, name);
    if (!ok)
        return;

    if (!std::isnan(m_lastTargetRA) && std::abs(raJ2000 - m_lastTargetRA) < 1e-9 &&
        std::abs(decJ2000 - m_lastTargetDec) < 1e-9)
        return; // unchanged since the last poll - don't republish every cycle

    m_lastTargetRA = raJ2000;
    m_lastTargetDec = decJ2000;

    // PiFinder's catalog coordinates are J2000 - precess to the mount's own
    // JNow (epoch-of-date) convention via libnova, the same library this
    // driver already links against for its own timekeeping. Matches this
    // project's established convention (PiFinder returns J2000, the
    // consumer precesses - see /api/current_target's own docstring, and
    // /api/fake_solve's equivalent convention in the opposite direction).
    ln_equ_posn meanPosition {raJ2000, decJ2000}; // /api/current_target already returns RA in degrees
    ln_equ_posn nowPosition {0, 0};
    const double jd = ln_get_julian_from_sys();
    ln_get_equ_prec(&meanPosition, jd, &nowPosition);

    TargetNP[0].setValue(nowPosition.ra / 15.0); // back to hours for INDI's own convention
    TargetNP[1].setValue(nowPosition.dec);
    TargetNP.setState(IPS_OK);
    TargetNP.apply();

    LOGF_INFO("On-device push-to target detected: %s (RA %.4fh, DEC %.4f deg, JNow).",
              name.c_str(), nowPosition.ra / 15.0, nowPosition.dec);
}

// See the header's own comment and this file's LX200_READ_ATTEMPT_TIMEOUT/
// LX200_READ_MAX_ATTEMPTS for why this retries instead of using one long
// LX200_TIMEOUT-second block per read.
int LX200_PIFINDER::readWithRetry(const char *data, char *response, int max_response_length)
{
    int rc = -1;
    for (int attempt = 0; attempt < LX200_READ_MAX_ATTEMPTS; ++attempt)
    {
        rc = setStandardProcedureAndReturnResponse(fd, data, response, max_response_length, LX200_READ_ATTEMPT_TIMEOUT);
        if (rc == 0)
            return 0;
    }
    return rc;
}

// PiFinder has no motor: "Goto" reuses PiFinder's existing SkySafari push-to
// mechanism. Sending :Sr#/:Sd# registers the target as a push-to object in
// the PiFinder UI (see PiFinder's pos_server.py parse_sr_command /
// parse_sd_command / handle_goto_command) - no PiFinder-side change needed.
bool LX200_PIFINDER::Goto(double ra, double dec)
{
    char data[64];
    int h, m, s;

    getSexComponents(ra, &h, &m, &s);
    snprintf(data, sizeof(data), ":Sr%02d:%02d:%02d#", h, m, s);
    if (0 != setStandardProcedureAndExpectChar(fd, data, "1"))
    {
        LOG_ERROR("Failed to set target RA on PiFinder.");
        return false;
    }

    getSexComponents(dec, &h, &m, &s);
    snprintf(data, sizeof(data), ":Sd%c%02d*%02d:%02d#", dec < 0 ? '-' : '+', abs(h), m, s);
    if (0 != setStandardProcedureAndExpectChar(fd, data, "1"))
    {
        LOG_ERROR("Failed to set target Dec on PiFinder.");
        return false;
    }

    LOG_INFO("Push-to target set on PiFinder.");
    TrackState = SCOPE_IDLE;

    // The base Telescope class publishes the requested (ra, dec) on its own
    // "TARGET_EOD_COORD" property right after this call returns true (see
    // INDI::Telescope::ISNewNumber) - that's the persistent, event-driven
    // signal the PiFinder Mount Bridge snoops to detect a new push-to
    // request, since ReadScopeStatus() itself never changes just because a
    // target was set (PiFinder has no motor).
    return true;
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

int LX200_PIFINDER::setStandardProcedureAndReturnResponse(int fd, const char *data, char *response, int max_response_length,
                                                            int timeoutSec)
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
    // PiFinder terminates every response with '#' and then sends nothing
    // more - tty_read() would block until max_response_length bytes arrive
    // (i.e. until timeoutSec expires) instead of returning as soon as the
    // short reply is complete. Read up to the terminator instead.
    error_type = tty_nread_section(fd, response, max_response_length, '#', timeoutSec, &nbytes_read);
    tcflush(fd, TCIFLUSH);

    if (nbytes_read < 1)
    {
        LOGF_ERROR("CMD <%s> read ERROR %d", data, error_type);
        return error_type;
    }

    return 0;
}
