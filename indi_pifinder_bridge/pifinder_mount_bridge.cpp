#include "pifinder_mount_bridge.h"
#include "pifinder_bridge_client.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <ctime>
#include <memory>

#include <curl/curl.h>
#include <nlohmann/json.hpp>

static std::unique_ptr<PiFinderMountBridge> pifinder_bridge(new PiFinderMountBridge());

namespace
{
// Single-threaded INDI driver (TimerHit callback style) - no explicit
// curl_global_init() needed, curl_easy_init() does it lazily on first use.
bool httpPostMountType(const std::string &url, const std::string &mountType)
{
    CURL *curl = curl_easy_init();
    if (curl == nullptr)
        return false;

    const std::string body = R"({"mount_type":")" + mountType + R"("})";

    struct curl_slist *headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());
    curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, 1500L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);

    const CURLcode res = curl_easy_perform(curl);
    long httpCode = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpCode);

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    return res == CURLE_OK && httpCode == 200;
}

size_t appendToString(char *ptr, size_t size, size_t nmemb, void *userdata)
{
    static_cast<std::string *>(userdata)->append(ptr, size * nmemb);
    return size * nmemb;
}

// Fetches PiFinder's own /api/status and extracts solve_source +
// last_solve_success - the position/status distinction from #107's
// root-cause writeup applies here too: LX200 (:GR#/:GD# - what
// getPiFinderRADE() reads) carries position only, no freshness/validity
// info at all, so this is fetched separately over HTTP instead of
// extending the LX200 wire protocol with a bespoke status command.
// Returns false on any request/parse failure - callers must treat that as
// "unknown", never as "fresh".
bool httpGetPiFinderSolveStatus(const std::string &url, std::string &solveSource, double &lastSolveSuccess)
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
        const auto &solution = parsed.at("solution");
        solveSource = solution.value("solve_source", std::string());
        const auto &lastSolveField = solution.at("last_solve_success");
        lastSolveSuccess = lastSolveField.is_null() ? 0.0 : lastSolveField.get<double>();
        return true;
    }
    catch (const nlohmann::json::exception &)
    {
        return false;
    }
}

// True only if PiFinder's currently-reported position came from a real
// camera solve (not IMU dead-reckoning, not a failed attempt) within
// maxAgeSeconds. Fails closed (false) on any HTTP/parse error - an
// automatic mount correction must never fire off data that couldn't be
// verified. See #79: Auto-correct previously corrected off a continuously
// IMU-interpolated position with no freshness check at all, chasing a
// target that kept moving between real solves.
// Fetches PiFinder's own /api/orientation_status (Mount Type +
// screen_direction/PiFinder Type, both read straight from config.json) -
// same request/response shape convention as httpGetPiFinderSolveStatus()
// above. Returns false on any request/parse failure.
bool httpGetPiFinderOrientation(const std::string &url, std::string &mountType, std::string &screenDirection)
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
        mountType = parsed.value("mount_type", std::string());
        screenDirection = parsed.value("screen_direction", std::string());
        return true;
    }
    catch (const nlohmann::json::exception &)
    {
        return false;
    }
}

bool isPiFinderSolveFresh(double maxAgeSeconds)
{
    std::string solveSource;
    double lastSolveSuccess = 0.0;
    const bool ok = httpGetPiFinderSolveStatus("http://127.0.0.1/api/status", solveSource, lastSolveSuccess) ||
                    httpGetPiFinderSolveStatus("http://127.0.0.1:8080/api/status", solveSource, lastSolveSuccess);
    if (!ok || solveSource != "CAM" || lastSolveSuccess <= 0.0)
        return false;

    const double ageSeconds = static_cast<double>(time(nullptr)) - lastSolveSuccess;
    return ageSeconds >= 0.0 && ageSeconds <= maxAgeSeconds;
}

} // namespace

PiFinderMountBridge::PiFinderMountBridge()
{
    setVersion(1, 1);
    setDriverInterface(AUX_INTERFACE);

    m_client.reset(new PiFinderBridgeClient());
}

const char *PiFinderMountBridge::getDefaultName()
{
    return "PiFinder Mount Bridge";
}

bool PiFinderMountBridge::initProperties()
{
    INDI::DefaultDevice::initProperties();

    IUFillText(&SettingsT[INDISERVER_HOST], "INDISERVER_HOST", "indiserver host", "localhost");
    IUFillText(&SettingsT[INDISERVER_PORT], "INDISERVER_PORT", "indiserver port", "7624");
    IUFillTextVector(&SettingsTP, SettingsT, 2, getDeviceName(), "BRIDGE_SETTINGS", "Settings",
                     "Options", IP_RW, 60, IPS_IDLE);

    IUFillText(&ActiveDeviceT[ACTIVE_PIFINDER], "ACTIVE_PIFINDER", "PiFinder", "PiFinder LX200");
    IUFillText(&ActiveDeviceT[ACTIVE_MOUNT], "ACTIVE_MOUNT", "Mount", "");
    IUFillTextVector(&ActiveDeviceTP, ActiveDeviceT, 2, getDeviceName(), "ACTIVE_DEVICES", "Active devices",
                     "Options", IP_RW, 60, IPS_IDLE);
    // Seeded from the same literals just passed to IUFillText() above, not
    // read back from ActiveDeviceT[...].text - that crashed live
    // (2026-08-05), apparently not yet populated at this point in this
    // libindi build. Whatever the reason, there's no need to read it back:
    // we just set it.
    m_lastActivePiFinder = "PiFinder LX200";
    m_lastActiveMount = "";

    IUFillText(&ShadowDeviceT[SHADOW_DEVICE], "SHADOW_DEVICE", "Shadow device", "PiFinder Simulator");
    IUFillTextVector(&ShadowDeviceTP, ShadowDeviceT, 1, getDeviceName(), "SHADOW_DEVICE_NAME",
                     "Shadow device", "Shadow Sync", IP_RW, 60, IPS_IDLE);

    IUFillSwitch(&ShadowSyncS[SHADOW_SYNC_ENABLE], "SHADOW_SYNC_ENABLE", "Enable", ISS_OFF);
    IUFillSwitch(&ShadowSyncS[SHADOW_SYNC_DISABLE], "SHADOW_SYNC_DISABLE", "Disable", ISS_ON);
    IUFillSwitchVector(&ShadowSyncSP, ShadowSyncS, 2, getDeviceName(), "SHADOW_SYNC", "Mirror to shadow device",
                       "Shadow Sync", IP_RW, ISR_1OFMANY, 60, IPS_IDLE);

    IUFillSwitch(&BridgeModeS[MODE_OFF], "MODE_OFF", "Off", ISS_ON);
    IUFillSwitch(&BridgeModeS[MODE_VERIFY_ALERT], "MODE_VERIFY_ALERT", "Verify/Alert only", ISS_OFF);
    IUFillSwitch(&BridgeModeS[MODE_AUTO_CORRECT], "MODE_AUTO_CORRECT", "Auto-correct on drift", ISS_OFF);
    IUFillSwitch(&BridgeModeS[MODE_GOTO_FORWARD], "MODE_GOTO_FORWARD", "Goto-Forward", ISS_OFF);
    IUFillSwitchVector(&BridgeModeSP, BridgeModeS, 4, getDeviceName(), "BRIDGE_MODE", "Coupling",
                       "Main Control", IP_RW, ISR_1OFMANY, 60, IPS_IDLE);

    IUFillSwitch(&CorrectionActionS[ACTION_SYNC], "ACTION_SYNC", "Sync", ISS_ON);
    IUFillSwitch(&CorrectionActionS[ACTION_GOTO], "ACTION_GOTO", "Goto/Track", ISS_OFF);
    IUFillSwitchVector(&CorrectionActionSP, CorrectionActionS, 2, getDeviceName(), "CORRECTION_ACTION",
                       "Auto-correct action", "Main Control", IP_RW, ISR_1OFMANY, 60, IPS_IDLE);

    IUFillSwitch(&ManualTriggerS[TRIGGER_SYNC_NOW], "TRIGGER_SYNC_NOW", "Sync Now", ISS_OFF);
    IUFillSwitch(&ManualTriggerS[TRIGGER_GOTO_NOW], "TRIGGER_GOTO_NOW", "Goto Now", ISS_OFF);
    IUFillSwitchVector(&ManualTriggerSP, ManualTriggerS, 2, getDeviceName(), "MANUAL_TRIGGER",
                       "Manual (one-shot)", "Main Control", IP_RW, ISR_ATMOST1, 60, IPS_IDLE);

    IUFillSwitch(&AbortMountS[0], "ABORT_MOUNT_NOW", "Stop movement", ISS_OFF);
    IUFillSwitchVector(&AbortMountSP, AbortMountS, 1, getDeviceName(), "ABORT_MOUNT",
                       "Emergency stop", "Main Control", IP_RW, ISR_ATMOST1, 0, IPS_IDLE);

    IUFillSwitch(&RepositionConfirmS[REPOSITION_CONFIRM_YES], "REPOSITION_CONFIRM_YES", "Adopt new position", ISS_OFF);
    IUFillSwitch(&RepositionConfirmS[REPOSITION_CONFIRM_NO], "REPOSITION_CONFIRM_NO", "Revert to held target", ISS_OFF);
    IUFillSwitchVector(&RepositionConfirmSP, RepositionConfirmS, 2, getDeviceName(), "REPOSITION_CONFIRM",
                       "Unexplained reposition", "Main Control", IP_RW, ISR_ATMOST1, 0, IPS_IDLE);

    IUFillSwitch(&TargetSourceS[TARGET_SOURCE_PIFINDER], "TARGET_SOURCE_PIFINDER", "PiFinder", ISS_ON);
    IUFillSwitch(&TargetSourceS[TARGET_SOURCE_MOUNT], "TARGET_SOURCE_MOUNT", "Mount", ISS_OFF);
    IUFillSwitchVector(&TargetSourceSP, TargetSourceS, 2, getDeviceName(), "TARGET_SOURCE",
                       "Following", "Main Control", IP_RO, ISR_1OFMANY, 0, IPS_IDLE);

    IUFillNumber(&DriftThresholdN[0], "THRESHOLD_ARCMIN", "Threshold (arcmin)", "%.1f", 0.1, 600, 0.5, 5);
    IUFillNumberVector(&DriftThresholdNP, DriftThresholdN, 1, getDeviceName(), "DRIFT_THRESHOLD",
                       "Drift Threshold", "Main Control", IP_RW, 60, IPS_IDLE);

    IUFillNumber(&MaxSyncDriftN[0], "MAX_SYNC_DRIFT_ARCMIN", "Max auto-Sync drift (arcmin)", "%.0f", 10, 10000, 10, 120);
    IUFillNumberVector(&MaxSyncDriftNP, MaxSyncDriftN, 1, getDeviceName(), "MAX_SYNC_DRIFT",
                       "Auto-Sync sanity limit", "Main Control", IP_RW, 60, IPS_IDLE);

    IUFillNumber(&SolveFreshnessMaxAgeN[0], "MAX_AGE_SEC", "Max solve age (s)", "%.1f", 0.5, 60, 0.5, 5);
    IUFillNumberVector(&SolveFreshnessMaxAgeNP, SolveFreshnessMaxAgeN, 1, getDeviceName(), "SOLVE_FRESHNESS",
                       "Auto-correct solve freshness", "Main Control", IP_RW, 60, IPS_IDLE);

    IUFillNumber(&DriftStatusN[0], "DRIFT_ARCMIN", "Current drift (arcmin)", "%.2f", 0, 10000, 0, 0);
    IUFillNumberVector(&DriftStatusNP, DriftStatusN, 1, getDeviceName(), "DRIFT_STATUS", "Status",
                       "Main Control", IP_RO, 60, IPS_IDLE);

    // Distinct from DriftStatusNP - that one means "the mount is tracking a
    // bit imprecisely, will self-correct". This means the mount refused a
    // Goto/Sync outright (e.g. an elevation or cable-wrap/axis limit), which
    // is what led to the balcony-wall incident: the software silently
    // accepted the refusal instead of telling the user. IPS_ALERT while a
    // refusal is active, IPS_OK once a subsequent attempt succeeds.
    IUFillText(&MountRejectT[0], "MESSAGE", "Message", "");
    IUFillTextVector(&MountRejectTP, MountRejectT, 1, getDeviceName(), "MOUNT_REJECT",
                       "Mount refused Goto/Sync", "Main Control", IP_RO, 60, IPS_IDLE);

    IUFillText(&PiFinderOrientationT[ORIENTATION_MOUNT_TYPE], "MOUNT_TYPE", "PiFinder's Mount Type", "");
    IUFillText(&PiFinderOrientationT[ORIENTATION_SCREEN_DIRECTION], "SCREEN_DIRECTION", "PiFinder Type", "");
    IUFillTextVector(&PiFinderOrientationTP, PiFinderOrientationT, 2, getDeviceName(), "PIFINDER_ORIENTATION",
                       "PiFinder Orientation", "Main Control", IP_RO, 60, IPS_IDLE);

    addDebugControl();
    setDefaultPollingPeriod(2000);

    return true;
}

void PiFinderMountBridge::ISGetProperties(const char *dev)
{
    DefaultDevice::ISGetProperties(dev);

    defineProperty(&SettingsTP);
    defineProperty(&ActiveDeviceTP);
    defineProperty(&ShadowDeviceTP);

    if (!m_configLoaded)
    {
        loadConfig(true);
        m_configLoaded = true;
    }
}

bool PiFinderMountBridge::updateProperties()
{
    DefaultDevice::updateProperties();

    if (isConnected())
    {
        defineProperty(&BridgeModeSP);
        defineProperty(&CorrectionActionSP);
        defineProperty(&ManualTriggerSP);
        defineProperty(&AbortMountSP);
        defineProperty(&DriftThresholdNP);
        defineProperty(&MaxSyncDriftNP);
        defineProperty(&SolveFreshnessMaxAgeNP);
        defineProperty(&DriftStatusNP);
        defineProperty(&MountRejectTP);
        defineProperty(&PiFinderOrientationTP);
        defineProperty(&ShadowSyncSP);
        defineProperty(&RepositionConfirmSP);
        defineProperty(&TargetSourceSP);

        // Restore the saved Coupling mode/threshold/etc. now that their
        // properties actually exist - see m_connectedConfigLoaded's
        // comment. Applies via the normal IUUpdateSwitch path, same as a
        // client sending it, so BridgeModeSP.s/IDSetSwitch etc. still fire
        // correctly.
        if (!m_connectedConfigLoaded)
        {
            loadConfig(true);
            m_connectedConfigLoaded = true;
        }
    }
    else
    {
        deleteProperty(BridgeModeSP.name);
        deleteProperty(CorrectionActionSP.name);
        deleteProperty(ManualTriggerSP.name);
        deleteProperty(AbortMountSP.name);
        deleteProperty(DriftThresholdNP.name);
        deleteProperty(MaxSyncDriftNP.name);
        deleteProperty(SolveFreshnessMaxAgeNP.name);
        deleteProperty(DriftStatusNP.name);
        deleteProperty(MountRejectTP.name);
        deleteProperty(PiFinderOrientationTP.name);
        deleteProperty(ShadowSyncSP.name);
        deleteProperty(RepositionConfirmSP.name);
        deleteProperty(TargetSourceSP.name);
    }

    return true;
}

bool PiFinderMountBridge::Connect()
{
    const std::string piFinderName = ActiveDeviceT[ACTIVE_PIFINDER].text;
    const std::string mountName = ActiveDeviceT[ACTIVE_MOUNT].text;

    if (mountName.empty())
    {
        LOG_ERROR("No mount device configured - set Active devices -> Mount first.");
        return false;
    }

    m_client->setServer(SettingsT[INDISERVER_HOST].text, std::stoi(SettingsT[INDISERVER_PORT].text));
    m_client->setDevices(piFinderName, mountName);
    m_client->setShadowDevice(ShadowDeviceT[SHADOW_DEVICE].text);

    if (!m_client->connectServer())
    {
        LOGF_ERROR("Failed to connect to indiserver at %s:%s", SettingsT[INDISERVER_HOST].text,
                   SettingsT[INDISERVER_PORT].text);
        return false;
    }

    LOGF_INFO("Bridging %s -> %s.", piFinderName.c_str(), mountName.c_str());
    SetTimer(getCurrentPollingPeriod());
    return true;
}

bool PiFinderMountBridge::Disconnect()
{
    m_client->disconnectServer();
    return true;
}

void PiFinderMountBridge::syncMountTypeToPiFinder()
{
    std::string mountType;
    if (!m_client || !m_client->getMountType(mountType))
        return;

    if (mountType == m_lastSyncedMountType)
        return;

    // PiFinder's web server falls back to 8080 if port 80 is already taken
    // (e.g. StellarMate's own nginx/dashboard) - same probe order the
    // gui_installer status page already uses for its OLED mirror.
    if (httpPostMountType("http://127.0.0.1/api/set_mount_type", mountType) ||
        httpPostMountType("http://127.0.0.1:8080/api/set_mount_type", mountType))
    {
        LOGF_INFO("Mount type '%s' pushed to PiFinder.", mountType.c_str());
        m_lastSyncedMountType = mountType;
    }
}

void PiFinderMountBridge::syncOrientationStatus()
{
    std::string piFinderMountType, screenDirection;
    const bool gotOrientation =
        httpGetPiFinderOrientation("http://127.0.0.1/api/orientation_status", piFinderMountType, screenDirection) ||
        httpGetPiFinderOrientation("http://127.0.0.1:8080/api/orientation_status", piFinderMountType, screenDirection);
    if (!gotOrientation)
        return; // PiFinder unreachable this tick - leave the last-known values/state showing rather than blank them

    std::string indiMountType;
    const bool haveIndiMountType = m_client && m_client->getMountType(indiMountType);

    // Both sides already use the exact same two-value vocabulary ("EQ"/
    // "Alt/Az") - see /api/set_mount_type's accepted values and
    // getMountType()'s own mapping - so this is a plain string compare, no
    // separate normalization needed.
    const bool mountTypeMatches = haveIndiMountType && indiMountType == piFinderMountType;

    const std::string key = piFinderMountType + "|" + screenDirection + "|" + (mountTypeMatches ? "1" : "0") +
                             "|" + (haveIndiMountType ? "1" : "0");
    if (key == m_lastOrientationStatusKey)
        return; // nothing changed since last publish - avoid redundant INDI traffic every tick

    m_lastOrientationStatusKey = key;
    IUSaveText(&PiFinderOrientationT[ORIENTATION_MOUNT_TYPE], piFinderMountType.c_str());
    IUSaveText(&PiFinderOrientationT[ORIENTATION_SCREEN_DIRECTION], screenDirection.c_str());
    // No INDI mount type known yet (not connected, or a driver that doesn't
    // report it) - IPS_IDLE rather than a false-positive IPS_ALERT, since
    // there's nothing to actually disagree with yet.
    PiFinderOrientationTP.s = !haveIndiMountType ? IPS_IDLE : (mountTypeMatches ? IPS_OK : IPS_ALERT);
    IDSetText(&PiFinderOrientationTP, nullptr);
}

bool PiFinderMountBridge::isShadowDeviceSafe() const
{
    const std::string shadowName = ShadowDeviceT[SHADOW_DEVICE].text;
    if (shadowName.empty())
        return false;

    // Must never fire if the shadow name happens to coincide with a real,
    // load-bearing device (typo, profile mixup, future reconfiguration) -
    // otherwise Shadow Sync would start Sync-ing the REAL mount or
    // PiFinder straight from PiFinder's raw live position, completely
    // bypassing Coupling's threshold/freshness/MaxSyncDrift gates. Found
    // via user pushback (2026-08-08) while designing the auto-arm below -
    // auto-arming removes the one manual "did I really mean to point this
    // there" pause a human had before, so this check has to stand in for
    // it unconditionally.
    if (shadowName == std::string(ActiveDeviceT[ACTIVE_MOUNT].text))
        return false;
    if (shadowName == std::string(ActiveDeviceT[ACTIVE_PIFINDER].text))
        return false;

    return true;
}

void PiFinderMountBridge::autoArmShadowSyncIfDevicePresent()
{
    // Auto-enables ShadowSyncSP the moment its target device is actually
    // present and safe to use - User decision (2026-08-08): keep the
    // manual switch (discoverable, real off-switch) rather than removing
    // it, but make sure nobody has to remember to (re-)flip it after every
    // driver restart. Fires once per device (re)appearance, not every
    // tick - m_shadowAutoArmed resets below once the device drops out
    // again, so reconnecting re-triggers auto-arm rather than leaving a
    // stale "already armed" flag across a device swap.
    if (!m_client->isShadowReady() || !isShadowDeviceSafe())
    {
        m_shadowAutoArmed = false;
        return;
    }

    if (m_shadowAutoArmed || ShadowSyncS[SHADOW_SYNC_ENABLE].s == ISS_ON)
    {
        m_shadowAutoArmed = true;
        return;
    }

    IUResetSwitch(&ShadowSyncSP);
    ShadowSyncS[SHADOW_SYNC_ENABLE].s = ISS_ON;
    ShadowSyncSP.s = IPS_OK;
    IDSetSwitch(&ShadowSyncSP, nullptr);
    saveConfig(true, ShadowSyncSP.name);
    m_shadowAutoArmed = true;
    LOGF_INFO("Shadow device '%s' detected - Shadow Sync auto-enabled.", ShadowDeviceT[SHADOW_DEVICE].text);
}

void PiFinderMountBridge::handleShadowSync()
{
    // Deliberately does not depend on m_client->isReady() (which requires
    // the real mount's properties too) - the shadow device (#181) must
    // work independent of ACTIVE_MOUNT/Coupling entirely, purely mirroring
    // PiFinder's own verified position for visualization. Also deliberately
    // never touches DriftStatusNP/exceeded/drift - those describe PiFinder
    // vs the *real* mount, unrelated to this.
    if (ShadowSyncS[SHADOW_SYNC_ENABLE].s != ISS_ON)
        return;

    if (!isShadowDeviceSafe())
        return;

    if (!m_client->isShadowReady())
        return;

    // Same freshness gate as every other automatic action here (#79) -
    // mirroring a stale/IMU-interpolated position would just teach the
    // shadow device to lie too, defeating the point of it being "truth".
    if (!isPiFinderSolveFresh(SolveFreshnessMaxAgeN[0].value))
        return;

    double piRA, piDec;
    if (!m_client->getPiFinderRADE(piRA, piDec))
        return;

    m_client->syncShadowCoords(piRA, piDec);
}

void PiFinderMountBridge::runModeReadinessCheck()
{
    if (BridgeModeS[MODE_OFF].s == ISS_ON)
        return; // nothing to verify - Coupling being Off is itself the "nothing needed" state

    if (!m_client->isReady())
    {
        // Not fixable here (needs the devices to actually connect) - just
        // make sure it's visible instead of silently doing nothing until
        // someone notices drift never updates. TimerHit()'s own isReady()
        // gate already handles this correctly once connected; this is
        // purely a heads-up at the moment the mode was chosen.
        LOG_WARN("Coupling mode enabled, but PiFinder and/or mount aren't both connected yet - "
                 "will start once ready.");
    }

    // A sanity limit smaller than the correction threshold would silently
    // block every correction whose drift falls between the two forever -
    // "exceeds threshold" but also "exceeds sanity cap", so it never syncs
    // and the GUI just shows a permanent, unexplained Alert. Safe to
    // auto-fix (raising a limit is strictly less restrictive, never a
    // safety regression) rather than just warn.
    if (MaxSyncDriftN[0].value < DriftThresholdN[0].value)
    {
        LOGF_WARN("Auto-Sync sanity limit (%.1f') was smaller than Threshold (%.1f') - corrections in "
                  "that gap could never fire. Raised the sanity limit to match.",
                  MaxSyncDriftN[0].value, DriftThresholdN[0].value);
        MaxSyncDriftN[0].value = DriftThresholdN[0].value;
        MaxSyncDriftNP.s = IPS_OK;
        IDSetNumber(&MaxSyncDriftNP, nullptr);
        saveConfig(true, MaxSyncDriftNP.name);
    }
}

bool PiFinderMountBridge::handleRepositionDetection(bool havePositions, double piRA, double piDec, double mountRA,
                                                     double mountDec, double drift)
{
    // --- A Fall-4 confirmation from a previous tick is still open: only check its timeout here. ---
    if (m_repositionConfirmPending)
    {
        if (time(nullptr) < m_repositionConfirmDeadline)
            return true; // still waiting on a response - don't let the old per-mode logic act meanwhile

        LOG_WARN("Reposition confirmation timed out - treating as unintentional, reverting to the held target.");
        m_repositionConfirmPending = false;
        IUResetSwitch(&RepositionConfirmSP);
        RepositionConfirmSP.s = IPS_ALERT;
        IDSetSwitch(&RepositionConfirmSP, nullptr);
        if (havePositions)
        {
            // Same Sync+re-Goto pattern HOLDING already uses for ordinary
            // drift - explicitly authorized past MaxSyncDriftNP this one
            // time, since a human-reviewable confirmation window just
            // expired unanswered rather than this being blind automation.
            //
            // Found live (2026-08-08): NOT routing this through the normal
            // SLEWING state caused an infinite loop - the next tick saw the
            // mount moving without weCommandedIt being true (misclassified
            // as ANOTHER external reposition), and marking "confirmed good"
            // immediately (before the Goto had actually converged) meant
            // any still-remaining residual looked implausible again right
            // away. Fixed: fire the same commands, but hand control back to
            // the existing SLEWING/SETTLING machinery to verify real
            // convergence (same discipline as every other correction path)
            // instead of declaring success ourselves. m_lastConfirmedGoodTime
            // is deliberately NOT touched here - it only updates once drift
            // is actually observed back within Threshold, same as normal.
            applySlewRateForDrift(drift);
            if (m_client->sendMountCoords(piRA, piDec, "SYNC") &&
                m_client->sendMountCoords(m_lastForwardedRA, m_lastForwardedDec, "TRACK"))
            {
                if (BridgeModeS[MODE_GOTO_FORWARD].s == ISS_ON)
                {
                    m_settleRetriesRemaining = MAX_SETTLE_RETRIES;
                    m_forwardState = ForwardState::SLEWING;
                }
                else
                {
                    m_correctSettleRetriesRemaining = MAX_SETTLE_RETRIES;
                    m_correctState = CorrectState::SLEWING;
                }
            }
        }
        return true;
    }

    if (!havePositions)
        return false;

    // --- Fall 2: mount moved without either of our own state machines having commanded it. ---
    const bool weCommandedIt = m_forwardState == ForwardState::SLEWING || m_correctState == CorrectState::SLEWING;

    // Onset detection: compare the mount's own position against the last
    // tick's, rather than watching isMountSlewing() (see m_lastPolledMountRA's
    // own comment in the header - a real external move can complete without
    // ever reporting IPS_BUSY at all). Skipped while we already know about
    // an in-progress external move (avoids re-triggering the log/settle
    // countdown every tick while it's still settling) and while we
    // commanded the current motion ourselves (that's a real, large,
    // expected delta - not Fall 2).
    if (!std::isnan(m_lastPolledMountRA) && !weCommandedIt && !m_externalSlewInProgress)
    {
        const double mountDeltaArcmin =
            angularSeparationArcmin(mountRA, mountDec, m_lastPolledMountRA, m_lastPolledMountDec);
        const double elapsedSec = std::max(0.0, static_cast<double>(time(nullptr) - m_lastPolledMountTime));
        const double maxPlausiblePassiveDrift = elapsedSec * MAX_SIDEREAL_DRIFT_ARCMIN_PER_SEC;

        if (mountDeltaArcmin > maxPlausiblePassiveDrift)
        {
            LOGF_INFO("Mount moved %.1f arcmin since the last check (~%.0fs ago, more than the %.1f' passive sky "
                      "motion could plausibly produce) without a command from Mount Bridge itself - external "
                      "control detected (hand-paddle, SkySafari, the OnStep app, or a mount-side GoTo). Will "
                      "adopt the new position once settled and confirmed by a fresh PiFinder solve.",
                      mountDeltaArcmin, elapsedSec, maxPlausiblePassiveDrift);
            m_externalSlewInProgress = true;
            m_externalSettleTicksRemaining = SETTLE_TICKS;
        }
    }
    m_lastPolledMountRA = mountRA;
    m_lastPolledMountDec = mountDec;
    m_lastPolledMountTime = time(nullptr);

    if (m_externalSlewInProgress)
    {
        if (m_externalSettleTicksRemaining > 0)
        {
            --m_externalSettleTicksRemaining;
            return true; // give the mount a few ticks to physically finish settling - isMountSlewing() can't be trusted to tell us (see above)
        }
        if (!isPiFinderSolveFresh(SolveFreshnessMaxAgeN[0].value))
            return true; // finished moving, but waiting for a fresh solve to confirm before trusting it (#79)

        m_externalSlewInProgress = false;
        m_lastForwardedRA = piRA;
        m_lastForwardedDec = piDec;
        m_correctTargetRA = piRA;
        m_correctTargetDec = piDec;
        m_lastConfirmedGoodTime = time(nullptr);
        m_forwardState = ForwardState::HOLDING;
        m_correctState = CorrectState::IDLE;
        setTargetSource(TARGET_SOURCE_MOUNT);
        LOGF_INFO("External reposition confirmed by a fresh PiFinder solve (RA %.4fh, DEC %.4f deg) - adopted "
                  "as the new held target.",
                  piRA, piDec);
        return true;
    }

    // Our own correction is already mid-flight (SLEWING/SETTLING) - let
    // handleGotoForward()/handleAutoCorrectGoto() manage it uninterrupted,
    // don't reclassify a transitional position as anything.
    if (weCommandedIt)
        return false;

    // --- Fall 3 vs Fall 4: no command signal seen, but PiFinder-vs-mount disagree past Threshold. ---
    // Never trust this drift number off a stale solve - same freshness gate
    // every other drift-consuming code path in this file already has
    // (SETTLING, HOLDING's own correction, CorrectState::SETTLING). Found
    // live (2026-08-08, #186 testing): right after Fall 1 forwards a
    // legitimate PushTo and the mount arrives, PiFinder's own reported
    // position hasn't necessarily been reconfirmed by a fresh solve yet -
    // without this gate, that transient (but real) mismatch got
    // misclassified as an implausible Fall-4 jump instead of just waiting
    // for the next solve like every other arrival-verification path does.
    if (!isPiFinderSolveFresh(SolveFreshnessMaxAgeN[0].value))
        return false;

    if (drift <= DriftThresholdN[0].value)
    {
        m_lastConfirmedGoodTime = time(nullptr); // currently agreeing - this moment is confirmed-good
        m_repositionBaselineTrusted = true;
        return false;
    }

    if (!m_repositionBaselineTrusted)
    {
        // Haven't observed a genuine confirmed-good moment since the last
        // reset (restart/mode-switch) yet - any pre-existing drift here
        // could simply be a backlog from being offline, not a sudden
        // implausible jump. Defer entirely to the existing HOLDING/Auto-
        // correct logic (still backstopped by MaxSyncDriftNP) until a real
        // baseline has actually been established.
        return false;
    }

    const double elapsedSec = static_cast<double>(time(nullptr) - m_lastConfirmedGoodTime);
    const double maxPlausibleDrift = elapsedSec * MAX_SIDEREAL_DRIFT_ARCMIN_PER_SEC;

    if (drift <= maxPlausibleDrift)
        return false; // Fall 3: physically plausible passive drift - let the existing HOLDING/Auto-correct logic handle it as before

    // Fall 4: exceeds what passive sky motion could produce in the elapsed
    // time - ask rather than guess (see docs/concepts/mount_bridge_reposition_detection.md UC4).
    m_repositionConfirmPending = true;
    m_repositionConfirmDeadline = time(nullptr) + REPOSITION_CONFIRM_TIMEOUT_SEC;
    RepositionConfirmSP.s = IPS_BUSY;
    IDSetSwitch(&RepositionConfirmSP, nullptr);
    LOGF_WARN("Drift %.1f arcmin exceeds what passive sky motion could produce in %.0fs (max plausible %.1f') - "
              "likely a deliberate reposition (e.g. clutch released) or a disturbance. Confirm via "
              "REPOSITION_CONFIRM within %ds, or it will be treated as unintentional and reverted automatically.",
              drift, elapsedSec, maxPlausibleDrift, REPOSITION_CONFIRM_TIMEOUT_SEC);
    return true;
}

void PiFinderMountBridge::TimerHit()
{
    if (!isConnected())
        return;

    syncMountTypeToPiFinder();
    syncOrientationStatus();
    autoArmShadowSyncIfDevicePresent();
    handleShadowSync();

    if (!m_client->isReady())
    {
        // #159: cold-start race - a watched device/property that hadn't
        // registered with indiserver yet when Connect() first ran could
        // otherwise sit "not ready" forever, indistinguishable from a real
        // functional bug (isReady() gates most of the driver's own
        // behavior, and nothing here previously explained why).
        if (m_client->retryMissingPropertiesIfNeeded())
            LOG_INFO("PiFinder/mount device properties not all available yet - retrying subscription.");
        else if (m_client->bindingGaveUp() && !m_bindingGiveUpLogged)
        {
            LOG_ERROR("PiFinder/mount device properties never became available - check Active "
                      "devices names match running drivers, or that both are actually connected. "
                      "Reconnect once confirmed.");
            m_bindingGiveUpLogged = true;
        }
        SetTimer(getCurrentPollingPeriod());
        return;
    }
    m_bindingGiveUpLogged = false;

    // Drift is computed and published whenever the bridge is ready
    // (PiFinder solving, mount connected), regardless of Coupling mode -
    // including Off. Found live (2026-08-05): the GUI's drift readout froze
    // at its startup default while Coupling was Off, which looked like a
    // broken readout rather than the intended "nothing is being watched"
    // state - Verify/Alert's compute-and-report behavior is really the
    // mode-independent baseline every other mode builds on, not a feature
    // exclusive to that one preset. Coupling mode still gates the *action*
    // (warn log, correction, forwarding) - Off stays inert there, just not
    // blind.
    double piRA, piDec, mountRA, mountDec;
    const bool havePositions =
        m_client->getPiFinderRADE(piRA, piDec) && m_client->getMountRADE(mountRA, mountDec);
    double drift = 0.0;
    bool exceeded = false;
    if (havePositions)
    {
        drift = angularSeparationArcmin(piRA, piDec, mountRA, mountDec);
        DriftStatusN[0].value = drift;
        const double threshold = DriftThresholdN[0].value;
        exceeded = drift > threshold;
        DriftStatusNP.s = exceeded ? IPS_ALERT : IPS_OK;
    }

    // Reposition Detection (#178) only applies to the two "held target"
    // Goto-based modes (Goto-Forward, Auto-correct's Goto action) - it
    // needs a held-target concept to adopt into, which Verify/Alert (never
    // touches the mount) and Auto-correct's plain Sync action (no target,
    // just continuous re-sync) don't have. See
    // docs/concepts/mount_bridge_reposition_detection.md.
    // Was emergency-disabled live (2026-08-08) after a false-positive
    // Fall-4 loop (see git history) - re-enabled after two fixes: reverts
    // now route through the normal SLEWING state instead of declaring
    // success immediately (so convergence is actually verified), and the
    // rate-based classification only activates after a genuine
    // confirmed-good baseline, not immediately after every restart.
    const bool repositionDetectionApplies =
        BridgeModeS[MODE_GOTO_FORWARD].s == ISS_ON ||
        (BridgeModeS[MODE_AUTO_CORRECT].s == ISS_ON && CorrectionActionS[ACTION_GOTO].s == ISS_ON);
    const bool repositionHandledThisTick =
        repositionDetectionApplies && handleRepositionDetection(havePositions, piRA, piDec, mountRA, mountDec, drift);

    if (repositionHandledThisTick)
    {
        // Fully handled above (external slew in progress/just adopted, or
        // a Fall-4 confirmation pending/just resolved) - skip the normal
        // per-mode logic so it can't act on the same drift a moment ago.
    }
    else if (BridgeModeS[MODE_GOTO_FORWARD].s == ISS_ON)
    {
        handleGotoForward();
    }
    else if (!havePositions)
    {
        // Nothing more to do this tick - PiFinder/mount coordinates aren't
        // available yet, same as before this changed to compute drift
        // unconditionally.
    }
    else if (BridgeModeS[MODE_VERIFY_ALERT].s == ISS_ON)
    {
        if (exceeded)
            LOGF_WARN("PiFinder and mount disagree by %.1f arcmin (threshold %.1f).", drift, DriftThresholdN[0].value);
    }
    else if (BridgeModeS[MODE_AUTO_CORRECT].s == ISS_ON)
    {
        if (CorrectionActionS[ACTION_GOTO].s == ISS_ON)
        {
            // Goto/Track correction: needs arrival-verify-and-refine, not a
            // one-shot fire-and-forget - see handleAutoCorrectGoto()'s
            // header comment for why (#170).
            handleAutoCorrectGoto(exceeded, piRA, piDec, drift, DriftThresholdN[0].value);
        }
        else if (exceeded && !isPiFinderSolveFresh(SolveFreshnessMaxAgeN[0].value))
        {
            // Found live (#79): correcting off a continuously
            // IMU-interpolated position (no real solve backing it, or one
            // older than SolveFreshnessMaxAgeN) chases a target that keeps
            // moving between real solves - the mount "oscillates" toward
            // wherever dead-reckoning currently thinks PiFinder points,
            // instead of a verified position. Skip the correction and wait
            // for the next tick's fresh-solve check instead.
            //
            // IPS_ALERT here (not IPS_OK) so the GUI can tell "exceeded but
            // gated" apart from "exceeded and actively correcting" - found
            // live (2026-08-05): the GUI's caption previously said
            // "Correcting the mount now" purely from drift > threshold, with
            // no way to know the driver was silently refusing underneath.
            DriftStatusNP.s = IPS_ALERT;
            LOGF_DEBUG(
                "Drift %.1f arcmin exceeded threshold, but PiFinder's position isn't backed by a solve "
                "within the last %.1fs - skipping correction.",
                drift, SolveFreshnessMaxAgeN[0].value);
        }
        else if (exceeded && drift > MaxSyncDriftN[0].value)
        {
            DriftStatusNP.s = IPS_ALERT;
            LOGF_WARN("Drift %.1f arcmin exceeds the auto-Sync sanity limit (%.1f) - skipping Sync to "
                      "avoid corrupting the mount's model off a possibly bad solve.",
                      drift, MaxSyncDriftN[0].value);
        }
        else if (exceeded)
        {
            // Sync path: instantaneous, no physical motion to verify/refine.
            DriftStatusNP.s = IPS_BUSY;
            if (m_client->sendMountCoords(piRA, piDec, "SYNC"))
                LOGF_INFO("Drift %.1f arcmin exceeded threshold - sent SYNC to mount.", drift);
            else
                LOG_ERROR("Failed to send correction to mount.");
        }
        // else: not exceeded - DriftStatusNP.s already set to IPS_OK by the
        // baseline computation above.
    }

    if (havePositions)
        IDSetNumber(&DriftStatusNP, nullptr);
    SetTimer(getCurrentPollingPeriod());
}

void PiFinderMountBridge::setMountRejectWarning(bool active, const std::string &message)
{
    const IPState newState = active ? IPS_ALERT : IPS_OK;
    const char *newText = active ? message.c_str() : "";

    // Avoid redundant INDI traffic/log noise every poll tick when nothing
    // changed - same reasoning as setTargetSource() below.
    if (MountRejectTP.s == newState && std::string(MountRejectT[0].text ? MountRejectT[0].text : "") == newText)
        return;

    IUSaveText(&MountRejectT[0], newText);
    MountRejectTP.s = newState;
    IDSetText(&MountRejectTP, nullptr);
}

void PiFinderMountBridge::setTargetSource(int index)
{
    if (TargetSourceS[index].s == ISS_ON)
        return; // already showing this - avoid redundant INDI traffic every tick
    IUResetSwitch(&TargetSourceSP);
    TargetSourceS[index].s = ISS_ON;
    TargetSourceSP.s = IPS_OK;
    IDSetSwitch(&TargetSourceSP, nullptr);
}

void PiFinderMountBridge::applySlewRateForDrift(double driftArcmin)
{
    const int count = m_client->getSlewRateCount();
    if (count <= 0)
        return; // driver doesn't expose slew rates - optional enhancement, not fatal to the Goto

    int index;
    if (driftArcmin > SLEW_RATE_FAR_THRESHOLD_ARCMIN)
        index = count - 1; // fastest available
    else if (driftArcmin > SLEW_RATE_CLOSE_THRESHOLD_ARCMIN)
        index = count / 2; // a middle rate
    else
        index = 0; // slowest/most precise available

    m_client->setSlewRateIndex(index);
}

void PiFinderMountBridge::handleGotoForward()
{
    double targetRA, targetDec;
    const bool hasTarget = m_client->getPiFinderTargetRADE(targetRA, targetDec);

    switch (m_forwardState)
    {
        case ForwardState::IDLE:
        {
            if (!hasTarget)
                return;

            if (!m_client->consumePiFinderTargetPending())
            {
                // No genuinely new Goto *event* since we started watching
                // (a BridgeMode switch, or a driver restart while this mode
                // was already active) - see consumePiFinderTargetPending()'s
                // own header comment for why this is event-based, not a
                // value comparison. Whatever target is already sitting here
                // is presumed stale/already acted on, not something to
                // blindly re-fire (found live 2026-08-09: turning Goto-
                // Forward on immediately re-slewed to the last-held target -
                // an earlier value-comparison approach here couldn't
                // reliably tell "stale" apart from "new").
                //
                // Still move to HOLDING rather than staying IDLE forever:
                // found live (2026-08-08) that a driver restart while
                // Goto-Forward was already active and holding a target left
                // the state machine permanently stuck in IDLE - nothing
                // "new" ever arrived, so drift went uncorrected indefinitely
                // (Altair drifted to 3.3' with no correction). HOLDING does
                // not fire anything on this tick either (no Goto here), but
                // from the *next* tick on it both actively re-checks drift/
                // threshold (self-correcting via the existing settle logic)
                // and applies this exact same pending-flag check itself, so
                // a subsequent genuinely new target still fires immediately.
                m_lastForwardedRA = targetRA;
                m_lastForwardedDec = targetDec;
                m_forwardState = ForwardState::HOLDING;
                return;
            }

            {
                double mountRA, mountDec;
                applySlewRateForDrift(m_client->getMountRADE(mountRA, mountDec)
                                          ? angularSeparationArcmin(targetRA, targetDec, mountRA, mountDec)
                                          : SLEW_RATE_FAR_THRESHOLD_ARCMIN + 1.0); // unknown - assume far, safe default
            }
            if (m_client->sendMountCoords(targetRA, targetDec, "TRACK"))
            {
                LOGF_INFO("New PiFinder target (RA %.4fh, DEC %.4f deg) - forwarded Goto to mount.",
                          targetRA, targetDec);
                setTargetSource(TARGET_SOURCE_PIFINDER);
                setMountRejectWarning(false, ""); // fresh attempt - any old warning no longer applies
                m_lastForwardedRA = targetRA;
                m_lastForwardedDec = targetDec;
                m_settleRetriesRemaining = MAX_SETTLE_RETRIES;
                m_forwardState = ForwardState::SLEWING;
            }
            else
            {
                LOG_ERROR("Failed to forward Goto to mount.");
            }
            break;
        }

        case ForwardState::SLEWING:
        {
            // Mirrors CorrectState::SLEWING's IPS_BUSY (#170) - lets the GUI
            // tell "actively slewing/correcting" apart from "holding", same
            // signal Auto-correct already gives. Previously left whatever
            // TimerHit's baseline drift computation set here (found live
            // 2026-08-08: the GUI caption for Goto-Forward was a static
            // string regardless of state - couldn't distinguish this from
            // "holding, drift exceeded").
            DriftStatusNP.s = IPS_BUSY;
            IDSetNumber(&DriftStatusNP, nullptr);
            if (!m_client->isMountSlewing())
            {
                m_settleTicksRemaining = SETTLE_TICKS;
                m_freshnessWaitTicksRemaining = MAX_FRESHNESS_WAIT_TICKS;
                m_forwardState = ForwardState::SETTLING;
                LOG_INFO("Mount finished slewing - waiting for a fresh PiFinder solve to verify arrival.");
            }
            break;
        }

        case ForwardState::SETTLING:
        {
            std::string rejectMsg;
            if (m_client->mountRejectedLastCoords(rejectMsg))
            {
                LOGF_WARN("Mount refused the Goto (%s) - likely an elevation or cable-wrap/axis limit, not just"
                          " settling. Not retrying the same command - now holding.",
                          rejectMsg.empty() ? "no message from driver" : rejectMsg.c_str());
                setMountRejectWarning(true, rejectMsg.empty() ? "Mount refused the Goto (no message from driver)" : rejectMsg);
                m_forwardState = ForwardState::HOLDING;
                break;
            }
            // Deliberately NOT clearing the warning just because *this tick*
            // saw no new rejection - mountRejectedLastCoords() is
            // consume-on-read, so it reads false on every tick after the one
            // that actually caught it. Clearing here would erase the warning
            // one tick after showing it, before a human ever sees it. Only
            // cleared below on a genuinely confirmed-good arrival.

            if (m_settleTicksRemaining > 0)
            {
                --m_settleTicksRemaining;
                break;
            }

            if (!isPiFinderSolveFresh(SolveFreshnessMaxAgeN[0].value))
            {
                // PiFinder hasn't produced a real camera solve since arrival
                // yet - see the header comment on m_freshnessWaitTicksRemaining.
                // Keep waiting rather than verifying/correcting off a guess.
                if (--m_freshnessWaitTicksRemaining <= 0)
                {
                    LOG_WARN("Gave up waiting for a fresh PiFinder solve after arrival - resuming normal holding.");
                    m_forwardState = ForwardState::HOLDING;
                }
                break;
            }

            double piRA, piDec, mountRA, mountDec;
            if (!m_client->getPiFinderRADE(piRA, piDec) || !m_client->getMountRADE(mountRA, mountDec))
            {
                m_forwardState = ForwardState::IDLE;
                break;
            }

            const double drift = angularSeparationArcmin(piRA, piDec, mountRA, mountDec);
            const double threshold = DriftThresholdN[0].value;
            DriftStatusN[0].value = drift;
            DriftStatusNP.s = (drift > threshold) ? IPS_ALERT : IPS_OK;
            IDSetNumber(&DriftStatusNP, nullptr);

            if (drift > MaxSyncDriftN[0].value)
            {
                // See MaxSyncDriftNP's header comment - a residual this
                // large is almost certainly a bad/outlier solve, not a
                // plausible alignment-model error. Don't Sync off it; hold
                // and keep re-checking on the next fresh solve instead.
                LOGF_WARN("Residual %.1f arcmin exceeds the auto-Sync sanity limit (%.1f) - not syncing,"
                          " will re-check on the next fresh solve.",
                          drift, MaxSyncDriftN[0].value);
                m_forwardState = ForwardState::HOLDING;
            }
            else if (drift > threshold && m_settleRetriesRemaining > 0)
            {
                // The mount already physically arrived via the Goto above,
                // but a residual this size usually means its own model was
                // slightly off at this sky position - Sync corrects that
                // model with PiFinder's more precise solve, then re-issuing
                // the Goto (now benefiting from the corrected model) should
                // land closer. Keep refining until within threshold or the
                // retry budget (MAX_SETTLE_RETRIES) runs out - unbounded
                // retries would chase solve noise forever if the residual
                // never actually clears.
                --m_settleRetriesRemaining;
                if (!m_client->sendMountCoords(piRA, piDec, "SYNC"))
                {
                    LOG_ERROR("Failed to send verification sync to mount.");
                    m_forwardState = ForwardState::IDLE;
                    break;
                }
                applySlewRateForDrift(drift);
                if (!m_client->sendMountCoords(m_lastForwardedRA, m_lastForwardedDec, "TRACK"))
                {
                    LOG_ERROR("Failed to re-issue Goto to mount after sync.");
                    m_forwardState = ForwardState::IDLE;
                    break;
                }
                LOGF_INFO("Arrival verified by PiFinder solve: residual %.1f arcmin exceeds threshold %.1f -"
                          " synced and re-issued Goto (%d attempt(s) left).",
                          drift, threshold, m_settleRetriesRemaining);
                m_forwardState = ForwardState::SLEWING;
            }
            else
            {
                if (drift > threshold)
                    LOGF_WARN("Gave up refining after %d attempt(s): residual %.1f arcmin still exceeds threshold %.1f - now holding, will retry on the next drift check.",
                              MAX_SETTLE_RETRIES, drift, threshold);
                else
                {
                    LOGF_INFO("Arrival verified by PiFinder solve: residual %.1f arcmin, within threshold %.1f - now holding.",
                              drift, threshold);
                    setMountRejectWarning(false, "");
                }
                m_forwardState = ForwardState::HOLDING;
            }
            break;
        }

        case ForwardState::HOLDING:
        {
            // A new push-to target always takes priority over continuing to
            // hold the old one - same pending-event check as IDLE (see
            // consumePiFinderTargetPending()'s header comment).
            if (hasTarget)
            {
                if (m_client->consumePiFinderTargetPending())
                {
                    {
                        double mountRA, mountDec;
                        applySlewRateForDrift(m_client->getMountRADE(mountRA, mountDec)
                                                  ? angularSeparationArcmin(targetRA, targetDec, mountRA, mountDec)
                                                  : SLEW_RATE_FAR_THRESHOLD_ARCMIN + 1.0);
                    }
                    if (m_client->sendMountCoords(targetRA, targetDec, "TRACK"))
                    {
                        LOGF_INFO("New PiFinder target (RA %.4fh, DEC %.4f deg) while holding - forwarded Goto to mount.",
                                  targetRA, targetDec);
                        setTargetSource(TARGET_SOURCE_PIFINDER);
                        setMountRejectWarning(false, ""); // fresh attempt - any old warning no longer applies
                        m_lastForwardedRA = targetRA;
                        m_lastForwardedDec = targetDec;
                        m_settleRetriesRemaining = MAX_SETTLE_RETRIES;
                        m_forwardState = ForwardState::SLEWING;
                    }
                    else
                    {
                        LOG_ERROR("Failed to forward Goto to mount.");
                    }
                    break;
                }
            }

            // If our own last correction is still physically executing,
            // skip this tick entirely - found live (2026-08-08): without
            // this, re-checking on the very next 2s poll tick could either
            // stack a new Sync+Goto on top of one still in flight, or read
            // piRA/mountRA mid-motion (transitional positions), teaching
            // the mount's model a bogus association via Sync. No fixed
            // settle-tick delay here (that was for verifying an uncertain
            // *new arrival* after a real slew, see SETTLING above) - a
            // continuous holding-correction is to a target we already
            // trust, so just wait for the mount to actually report done.
            if (m_client->isMountSlewing())
            {
                DriftStatusNP.s = IPS_BUSY;
                IDSetNumber(&DriftStatusNP, nullptr);
                break;
            }

            {
                std::string rejectMsg;
                if (m_client->mountRejectedLastCoords(rejectMsg))
                {
                    LOGF_WARN("Mount refused the correction (%s) - likely an elevation or cable-wrap/axis limit."
                              " Not retrying the same command this tick.",
                              rejectMsg.empty() ? "no message from driver" : rejectMsg.c_str());
                    setMountRejectWarning(true, rejectMsg.empty() ? "Mount refused the correction (no message from driver)" : rejectMsg);
                    break;
                }
                // Same reasoning as SETTLING above - not cleared here, only
                // on a genuinely confirmed-good drift check below.
            }

            // Still the same held target - watch for it drifting past
            // Threshold (e.g. ordinary mount tracking imperfection) and
            // correct exactly like SETTLING does, just re-triggerable
            // indefinitely instead of only right after arrival. Same
            // freshness gate as everywhere else - never correct off a
            // guessed/stale position.
            if (!isPiFinderSolveFresh(SolveFreshnessMaxAgeN[0].value))
                break;

            double piRA, piDec, mountRA, mountDec;
            if (!m_client->getPiFinderRADE(piRA, piDec) || !m_client->getMountRADE(mountRA, mountDec))
                break;

            const double drift = angularSeparationArcmin(piRA, piDec, mountRA, mountDec);
            const double threshold = DriftThresholdN[0].value;
            DriftStatusN[0].value = drift;
            DriftStatusNP.s = (drift > threshold) ? IPS_ALERT : IPS_OK;
            IDSetNumber(&DriftStatusNP, nullptr);

            if (drift <= threshold)
            {
                setMountRejectWarning(false, "");
                break;
            }

            if (drift > MaxSyncDriftN[0].value)
            {
                // See MaxSyncDriftNP's header comment - stay in HOLDING and
                // keep watching rather than syncing off a likely-bad solve.
                LOGF_WARN("Held target drifted %.1f arcmin, exceeding the auto-Sync sanity limit (%.1f) -"
                          " not syncing, will re-check on the next fresh solve.",
                          drift, MaxSyncDriftN[0].value);
                break;
            }

            applySlewRateForDrift(drift);
            if (!m_client->sendMountCoords(piRA, piDec, "SYNC"))
            {
                LOG_ERROR("Failed to send verification sync to mount while holding.");
                break;
            }
            if (!m_client->sendMountCoords(m_lastForwardedRA, m_lastForwardedDec, "TRACK"))
            {
                LOG_ERROR("Failed to re-issue Goto to mount while holding.");
                break;
            }
            // Deliberately stays in HOLDING (no SLEWING/SETTLING detour) -
            // the isMountSlewing() check above on the next tick is the only
            // gate needed; retrying indefinitely every tick drift still
            // exceeds threshold is the intended "hold" behavior, not a
            // bounded settle attempt to give up on.
            DriftStatusNP.s = IPS_BUSY;
            IDSetNumber(&DriftStatusNP, nullptr);
            LOGF_INFO("Held target drifted %.1f arcmin past threshold %.1f - synced and re-issued Goto to hold it.",
                      drift, threshold);
            break;
        }
    }
}

void PiFinderMountBridge::handleAutoCorrectGoto(bool exceeded, double piRA, double piDec, double drift, double threshold)
{
    switch (m_correctState)
    {
        case CorrectState::IDLE:
        {
            if (!exceeded)
                return;

            if (!isPiFinderSolveFresh(SolveFreshnessMaxAgeN[0].value))
            {
                DriftStatusNP.s = IPS_ALERT;
                LOGF_DEBUG(
                    "Drift %.1f arcmin exceeded threshold, but PiFinder's position isn't backed by a solve "
                    "within the last %.1fs - skipping correction.",
                    drift, SolveFreshnessMaxAgeN[0].value);
                return;
            }

            DriftStatusNP.s = IPS_BUSY;
            applySlewRateForDrift(drift);
            if (m_client->sendMountCoords(piRA, piDec, "TRACK"))
            {
                LOGF_INFO("Drift %.1f arcmin exceeded threshold - sent Goto to mount.", drift);
                m_correctTargetRA = piRA;
                m_correctTargetDec = piDec;
                m_correctSettleRetriesRemaining = MAX_SETTLE_RETRIES;
                m_correctState = CorrectState::SLEWING;
                setMountRejectWarning(false, ""); // fresh attempt - any old warning no longer applies
            }
            else
            {
                LOG_ERROR("Failed to send correction to mount.");
            }
            break;
        }

        case CorrectState::SLEWING:
        {
            // A Goto correction takes far longer than one poll tick to
            // complete, and "drift still exceeds threshold" stays true for
            // the whole time the mount is slewing toward it - stay BUSY and
            // just wait for it to finish rather than re-issuing (which most
            // mount drivers handle by aborting the in-progress slew and
            // starting over).
            DriftStatusNP.s = IPS_BUSY;
            if (!m_client->isMountSlewing())
            {
                m_correctSettleTicksRemaining = SETTLE_TICKS;
                m_correctFreshnessWaitTicksRemaining = MAX_FRESHNESS_WAIT_TICKS;
                m_correctState = CorrectState::SETTLING;
                LOG_INFO("Auto-correct Goto finished slewing - waiting for a fresh PiFinder solve to verify arrival.");
            }
            break;
        }

        case CorrectState::SETTLING:
        {
            DriftStatusNP.s = IPS_BUSY;

            {
                std::string rejectMsg;
                if (m_client->mountRejectedLastCoords(rejectMsg))
                {
                    LOGF_WARN("Mount refused the auto-correct Goto (%s) - likely an elevation or"
                              " cable-wrap/axis limit, not just settling. Not retrying the same command -"
                              " resuming normal monitoring.",
                              rejectMsg.empty() ? "no message from driver" : rejectMsg.c_str());
                    setMountRejectWarning(true, rejectMsg.empty() ? "Mount refused the auto-correct Goto (no message from driver)" : rejectMsg);
                    m_correctState = CorrectState::IDLE;
                    break;
                }
                // Same reasoning as ForwardState::SETTLING above - not
                // cleared here, only on a genuinely confirmed-good residual
                // check below.
            }

            if (m_correctSettleTicksRemaining > 0)
            {
                --m_correctSettleTicksRemaining;
                break;
            }

            if (!isPiFinderSolveFresh(SolveFreshnessMaxAgeN[0].value))
            {
                // See m_freshnessWaitTicksRemaining's comment on ForwardState
                // - same reasoning applies here: trusting an IMU-interpolated
                // "arrival" position would Sync the mount to a guessed
                // position instead of a verified one.
                if (--m_correctFreshnessWaitTicksRemaining <= 0)
                {
                    LOG_WARN("Gave up waiting for a fresh PiFinder solve after auto-correct Goto - resuming normal monitoring.");
                    m_correctState = CorrectState::IDLE;
                }
                break;
            }

            // drift/threshold reflect this tick's freshly-computed
            // separation (passed in from TimerHit), i.e. the actual residual
            // now that the mount has stopped and PiFinder has a fresh solve.
            if (drift > MaxSyncDriftN[0].value)
            {
                // See MaxSyncDriftNP's header comment - don't Sync off a
                // likely-bad solve; fall back to normal monitoring instead.
                LOGF_WARN("Auto-correct residual %.1f arcmin exceeds the auto-Sync sanity limit (%.1f) -"
                          " not syncing, resuming normal monitoring.",
                          drift, MaxSyncDriftN[0].value);
                m_correctState = CorrectState::IDLE;
            }
            else if (drift > threshold && m_correctSettleRetriesRemaining > 0)
            {
                // The mount already physically arrived via the Goto above,
                // but a residual this size usually means its own alignment
                // model was slightly off at this sky position - blindly
                // re-issuing Goto to a corrected RA/Dec never fixes that (see
                // #170: drift kept climbing right back up after each
                // "correction"). Sync first to fix the model with PiFinder's
                // verified solve, then re-issue the Goto so it benefits from
                // the corrected model. Bounded so a genuinely noisy solve
                // can't loop forever chasing it.
                --m_correctSettleRetriesRemaining;
                if (!m_client->sendMountCoords(piRA, piDec, "SYNC"))
                {
                    LOG_ERROR("Failed to send verification sync to mount.");
                    m_correctState = CorrectState::IDLE;
                    break;
                }
                applySlewRateForDrift(drift);
                if (!m_client->sendMountCoords(m_correctTargetRA, m_correctTargetDec, "TRACK"))
                {
                    LOG_ERROR("Failed to re-issue Goto to mount after sync.");
                    m_correctState = CorrectState::IDLE;
                    break;
                }
                LOGF_INFO("Auto-correct arrival verified by PiFinder solve: residual %.1f arcmin exceeds threshold %.1f -"
                          " synced and re-issued Goto (%d attempt(s) left).",
                          drift, threshold, m_correctSettleRetriesRemaining);
                m_correctState = CorrectState::SLEWING;
            }
            else
            {
                if (drift > threshold)
                    LOGF_WARN("Auto-correct gave up refining after %d attempt(s): residual %.1f arcmin still exceeds threshold %.1f.",
                              MAX_SETTLE_RETRIES, drift, threshold);
                else
                {
                    LOGF_INFO("Auto-correct arrival verified by PiFinder solve: residual %.1f arcmin, within threshold %.1f.",
                              drift, threshold);
                    setMountRejectWarning(false, "");
                }
                m_correctState = CorrectState::IDLE;
            }
            break;
        }
    }
}

bool PiFinderMountBridge::ISNewSwitch(const char *dev, const char *name, ISState *states, char *names[], int n)
{
    if (dev != nullptr && strcmp(dev, getDeviceName()) == 0)
    {
        if (strcmp(name, BridgeModeSP.name) == 0)
        {
            IUUpdateSwitch(&BridgeModeSP, states, names, n);
            BridgeModeSP.s = IPS_OK;
            IDSetSwitch(&BridgeModeSP, nullptr);

            // Any mode change resets the Goto-Forward state machine, so
            // re-entering it always re-baselines against whatever target
            // PiFinder currently has instead of reacting to a stale one.
            //
            // Discard any pending target-update event from before this
            // switch - handleGotoForward()'s IDLE case (see its own comment)
            // now reacts to a genuinely new Goto *event*
            // (consumePiFinderTargetPending(), edge-triggered) rather than
            // comparing RA/Dec values, so this is a plain "start listening
            // from here" reset, not a value snapshot. This replaces an
            // earlier value-snapshot version of this fix (2026-08-09) that
            // turned out unsafe live: turning Goto-Forward on immediately
            // re-slewed to the mount's last-held target, because a value
            // comparison alone can't reliably tell "stale target already
            // sitting there" apart from "genuinely new" (see
            // pifinder_bridge_client.h's consumePiFinderTargetPending() for
            // why an event-based signal fixes that). A target that was
            // already there before this switch produces no new event and is
            // correctly ignored; picking the very same object again in
            // KStars right after switching modes still fires immediately,
            // since that click produces a fresh event regardless of value.
            m_forwardState = ForwardState::IDLE;
            m_client->consumePiFinderTargetPending();

            // Sync the mount to PiFinder's current position once, right when
            // entering Goto-Forward - gives the mount's own model a known-
            // good alignment reference before any Goto is ever forwarded,
            // the same way you'd sync a real scope to a known star before
            // doing GoTos elsewhere (direct live feedback, 2026-08-09: "At a
            // Goto Start I should do a 'sync mount from PiFinder' first").
            // Gated on solve freshness (same isPiFinderSolveFresh() check
            // Auto-correct already uses) - only trust PiFinder's live
            // position as a sync reference if it's backed by a recent real
            // camera solve, not a stale/IMU-only guess. Found live the same
            // session: syncing off a frozen Injected-Solve position (the
            // physical unit wasn't actually moving with the test mount)
            // would have synced the mount to a meaningless reference -
            // skipping when not fresh is deliberate, not a gap to "fix" by
            // relaxing this check.
            if (BridgeModeS[MODE_GOTO_FORWARD].s == ISS_ON)
            {
                double piRA, piDec;
                if (m_client->getPiFinderRADE(piRA, piDec) && isPiFinderSolveFresh(SolveFreshnessMaxAgeN[0].value))
                {
                    if (m_client->sendMountCoords(piRA, piDec, "SYNC"))
                        LOGF_INFO("Synced mount to PiFinder's current position (RA %.4fh, DEC %.4f deg) on entering Goto-Forward.",
                                  piRA, piDec);
                    else
                        LOG_WARN("Failed to sync mount to PiFinder's position on entering Goto-Forward.");
                }
            }

            // Same idea for Auto-Correct's Goto-refine state machine - don't
            // let an in-progress settle/retry cycle from a previous mode
            // silently keep running (or resume stale) after switching away
            // and back.
            m_correctState = CorrectState::IDLE;

            // Same for Reposition Detection's own tracking (#178) - don't
            // let a stale "watching an external slew" or "confirmation
            // pending" state, or an outdated drift-rate baseline, survive a
            // mode switch.
            m_externalSlewInProgress = false;
            m_lastConfirmedGoodTime = 0;
            m_repositionBaselineTrusted = false;
            if (m_repositionConfirmPending)
            {
                m_repositionConfirmPending = false;
                IUResetSwitch(&RepositionConfirmSP);
                RepositionConfirmSP.s = IPS_IDLE;
                IDSetSwitch(&RepositionConfirmSP, nullptr);
            }

            // Persist so the chosen mode actually survives a reconnect -
            // see m_connectedConfigLoaded's comment. Without this, the
            // saved config just keeps replaying whatever was last actively
            // saved (typically Off/Verify-Alert from ages ago) regardless
            // of what the user picks live, same "selection doesn't stick"
            // shape as #158's ACTIVE_DEVICES bug.
            saveConfig(true, BridgeModeSP.name);
            runModeReadinessCheck();
            return true;
        }

        if (strcmp(name, CorrectionActionSP.name) == 0)
        {
            IUUpdateSwitch(&CorrectionActionSP, states, names, n);
            CorrectionActionSP.s = IPS_OK;
            IDSetSwitch(&CorrectionActionSP, nullptr);

            // Switching Sync<->Goto mid-correction shouldn't leave a stale
            // settle/retry cycle running for the action that's no longer
            // selected.
            m_correctState = CorrectState::IDLE;
            return true;
        }

        if (strcmp(name, ManualTriggerSP.name) == 0)
        {
            IUUpdateSwitch(&ManualTriggerSP, states, names, n);
            const bool wantSync = ManualTriggerS[TRIGGER_SYNC_NOW].s == ISS_ON;
            const bool wantGoto = ManualTriggerS[TRIGGER_GOTO_NOW].s == ISS_ON;

            if (wantSync || wantGoto)
            {
                double piRA, piDec;
                if (!m_client->isReady() || !m_client->getPiFinderRADE(piRA, piDec))
                {
                    LOG_ERROR("Not ready - PiFinder or mount device/properties not available yet.");
                    ManualTriggerSP.s = IPS_ALERT;
                }
                else
                {
                    const char *coordSet = wantGoto ? "TRACK" : "SYNC";
                    if (m_client->sendMountCoords(piRA, piDec, coordSet))
                    {
                        LOGF_INFO("Manual %s sent to mount.", coordSet);
                        ManualTriggerSP.s = IPS_OK;
                    }
                    else
                    {
                        LOG_ERROR("Failed to send manual correction to mount.");
                        ManualTriggerSP.s = IPS_ALERT;
                    }
                }
            }

            IUResetSwitch(&ManualTriggerSP);
            IDSetSwitch(&ManualTriggerSP, nullptr);
            return true;
        }

        if (strcmp(name, ShadowSyncSP.name) == 0)
        {
            IUUpdateSwitch(&ShadowSyncSP, states, names, n);
            ShadowSyncSP.s = IPS_OK;
            IDSetSwitch(&ShadowSyncSP, nullptr);
            saveConfig(true, ShadowSyncSP.name);
            return true;
        }

        if (strcmp(name, AbortMountSP.name) == 0)
        {
            IUUpdateSwitch(&AbortMountSP, states, names, n);

            if (AbortMountS[0].s == ISS_ON)
            {
                // Deliberately not gated on m_client->isReady() - see
                // abortMount()'s own comment, this must work even if
                // PiFinder's side is unavailable/stale.
                if (m_client->abortMount())
                {
                    LOG_WARN("Emergency stop: sent ABORT to the mount.");
                    AbortMountSP.s = IPS_OK;
                }
                else
                {
                    LOG_ERROR("Emergency stop: mount not available - could not send ABORT.");
                    AbortMountSP.s = IPS_ALERT;
                }
            }

            IUResetSwitch(&AbortMountSP);
            IDSetSwitch(&AbortMountSP, nullptr);
            return true;
        }

        if (strcmp(name, RepositionConfirmSP.name) == 0)
        {
            IUUpdateSwitch(&RepositionConfirmSP, states, names, n);

            if (!m_repositionConfirmPending)
            {
                LOG_WARN("No reposition confirmation is currently pending.");
                RepositionConfirmSP.s = IPS_ALERT;
            }
            else if (RepositionConfirmS[REPOSITION_CONFIRM_YES].s == ISS_ON)
            {
                double piRA, piDec;
                if (m_client->getPiFinderRADE(piRA, piDec))
                {
                    m_lastForwardedRA = piRA;
                    m_lastForwardedDec = piDec;
                    m_correctTargetRA = piRA;
                    m_correctTargetDec = piDec;
                    m_forwardState = ForwardState::HOLDING;
                    m_correctState = CorrectState::IDLE;
                    m_lastConfirmedGoodTime = time(nullptr);
                    setTargetSource(TARGET_SOURCE_MOUNT);
                    LOGF_INFO("Reposition confirmed - adopted (RA %.4fh, DEC %.4f deg) as the new held target.",
                              piRA, piDec);
                    RepositionConfirmSP.s = IPS_OK;
                }
                else
                {
                    LOG_ERROR("Could not read PiFinder's position to adopt - not ready.");
                    RepositionConfirmSP.s = IPS_ALERT;
                }
                m_repositionConfirmPending = false;
            }
            else if (RepositionConfirmS[REPOSITION_CONFIRM_NO].s == ISS_ON)
            {
                double piRA, piDec;
                if (m_client->getPiFinderRADE(piRA, piDec))
                {
                    // Same fix as the timeout path above (see its comment) -
                    // route through the normal SLEWING state so the existing
                    // SETTLING logic verifies real convergence, instead of
                    // declaring success immediately.
                    applySlewRateForDrift(angularSeparationArcmin(piRA, piDec, m_lastForwardedRA, m_lastForwardedDec));
                    if (m_client->sendMountCoords(piRA, piDec, "SYNC") &&
                        m_client->sendMountCoords(m_lastForwardedRA, m_lastForwardedDec, "TRACK"))
                    {
                        if (BridgeModeS[MODE_GOTO_FORWARD].s == ISS_ON)
                        {
                            m_settleRetriesRemaining = MAX_SETTLE_RETRIES;
                            m_forwardState = ForwardState::SLEWING;
                        }
                        else
                        {
                            m_correctSettleRetriesRemaining = MAX_SETTLE_RETRIES;
                            m_correctState = CorrectState::SLEWING;
                        }
                    }
                    LOG_INFO("Reposition declined - reverting to the held target.");
                    RepositionConfirmSP.s = IPS_OK;
                }
                else
                {
                    LOG_ERROR("Could not read PiFinder's position to revert from - not ready.");
                    RepositionConfirmSP.s = IPS_ALERT;
                }
                m_repositionConfirmPending = false;
            }

            IUResetSwitch(&RepositionConfirmSP);
            IDSetSwitch(&RepositionConfirmSP, nullptr);
            return true;
        }
    }

    return DefaultDevice::ISNewSwitch(dev, name, states, names, n);
}

bool PiFinderMountBridge::ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n)
{
    if (dev != nullptr && strcmp(dev, getDeviceName()) == 0)
    {
        if (strcmp(name, SettingsTP.name) == 0)
        {
            IUUpdateText(&SettingsTP, texts, names, n);
            SettingsTP.s = IPS_OK;
            IDSetText(&SettingsTP, nullptr);
            return true;
        }

        if (strcmp(name, ActiveDeviceTP.name) == 0)
        {
            IUUpdateText(&ActiveDeviceTP, texts, names, n);
            ActiveDeviceTP.s = IPS_OK;
            IDSetText(&ActiveDeviceTP, nullptr);

            // Compared against m_lastActive*, not a pre-update snapshot of
            // ActiveDeviceT[...].text - crashed live (2026-08-05) reading
            // that field's raw char* into a std::string here, apparently
            // reentered via loadConfig()'s config replay inside
            // ISGetProperties() at a point where it wasn't yet safe to
            // read. m_lastActive* is always a valid owned string (seeded
            // from the same defaults in initProperties()), so this needs
            // no null-checks and only reads ActiveDeviceT[...].text after
            // IUUpdateText() has just populated it from the incoming,
            // known-valid texts[] array.
            const std::string newPiFinder = ActiveDeviceT[ACTIVE_PIFINDER].text;
            const std::string newMount = ActiveDeviceT[ACTIVE_MOUNT].text;
            const bool changed = newPiFinder != m_lastActivePiFinder || newMount != m_lastActiveMount;
            m_lastActivePiFinder = newPiFinder;
            m_lastActiveMount = newMount;

            // Found live (#158): changing which device is watched here used to
            // be cosmetic while already connected - m_client's watchDevice()
            // subscriptions were only ever established once, inside Connect(),
            // so re-pointing ActiveDeviceTP at a different mount mid-session
            // updated what the property *displayed* but left the embedded
            // client silently bound to whichever device was active at the
            // last Connect(). isReady() then depended on properties from a
            // device nobody was watching anymore - MANUAL_TRIGGER went
            // straight to Alert ("not ready"), and TimerHit()'s isReady()
            // gate blocked the drift/correction logic entirely, with nothing
            // in the log to explain why. Cycling the connection re-runs
            // Connect()'s setDevices() against the new names, the same
            // recovery a full disconnect/reconnect (or driver restart)
            // already provided manually.
            //
            // The `changed` guard is not optional: found live (2026-08-05)
            // that some other INDI client (KStars/Ekos, the Web Manager, or
            // this driver's own profile-load cycle) periodically re-asserts
            // ActiveDeviceTP with its *current, unchanged* values as routine
            // INDI traffic - completely normal, but the original fix reacted
            // to *any* ISNewText call for this vector, not just an actual
            // value change, so it disconnected and reconnected every single
            // time that happened - a self-inflicted periodic drop that
            // looked identical to "something else keeps killing the
            // connection" from the outside.
            if (changed && isConnected())
            {
                LOG_INFO("Active devices changed - reconnecting to apply.");
                Disconnect();
                Connect();
            }
            return true;
        }

        if (strcmp(name, ShadowDeviceTP.name) == 0)
        {
            IUUpdateText(&ShadowDeviceTP, texts, names, n);
            ShadowDeviceTP.s = IPS_OK;
            IDSetText(&ShadowDeviceTP, nullptr);

            // Rebinds only the client's shadow-device watch, not the whole
            // session - deliberately not a Disconnect()/Connect() cycle
            // like ActiveDeviceTP above. The shadow device is independent
            // of the real PiFinder/mount coupling (#181); re-pointing it
            // must never interrupt an in-progress correction/settle cycle
            // on the real mount.
            if (isConnected())
                m_client->setShadowDevice(ShadowDeviceT[SHADOW_DEVICE].text);
            return true;
        }
    }

    return DefaultDevice::ISNewText(dev, name, texts, names, n);
}

bool PiFinderMountBridge::ISNewNumber(const char *dev, const char *name, double values[], char *names[], int n)
{
    if (dev != nullptr && strcmp(dev, getDeviceName()) == 0)
    {
        if (strcmp(name, DriftThresholdNP.name) == 0)
        {
            IUUpdateNumber(&DriftThresholdNP, values, names, n);
            DriftThresholdNP.s = IPS_OK;
            IDSetNumber(&DriftThresholdNP, nullptr);
            // Found live (2026-08-09): unlike MaxSyncDriftNP/BridgeModeSP/
            // ShadowSyncSP just above/below, this handler never persisted
            // the change - a user-set Threshold silently reverted to the
            // compiled-in default (5) on the next driver restart, with
            // nothing in the GUI explaining why. Same auto-save-on-change
            // pattern as those, just missing here.
            saveConfig(true, DriftThresholdNP.name);
            return true;
        }

        if (strcmp(name, MaxSyncDriftNP.name) == 0)
        {
            IUUpdateNumber(&MaxSyncDriftNP, values, names, n);
            MaxSyncDriftNP.s = IPS_OK;
            IDSetNumber(&MaxSyncDriftNP, nullptr);
            // Same gap as DriftThresholdNP above (2026-08-09) - found while
            // fixing that one, same missing auto-save.
            saveConfig(true, MaxSyncDriftNP.name);
            return true;
        }

        if (strcmp(name, SolveFreshnessMaxAgeNP.name) == 0)
        {
            IUUpdateNumber(&SolveFreshnessMaxAgeNP, values, names, n);
            SolveFreshnessMaxAgeNP.s = IPS_OK;
            IDSetNumber(&SolveFreshnessMaxAgeNP, nullptr);
            // Same gap as DriftThresholdNP above (2026-08-09) - found while
            // fixing that one, same missing auto-save.
            saveConfig(true, SolveFreshnessMaxAgeNP.name);
            return true;
        }
    }

    return DefaultDevice::ISNewNumber(dev, name, values, names, n);
}

bool PiFinderMountBridge::saveConfigItems(FILE *fp)
{
    IUSaveConfigText(fp, &SettingsTP);
    IUSaveConfigText(fp, &ActiveDeviceTP);
    IUSaveConfigText(fp, &ShadowDeviceTP);
    IUSaveConfigSwitch(fp, &ShadowSyncSP);
    IUSaveConfigSwitch(fp, &BridgeModeSP);
    IUSaveConfigSwitch(fp, &CorrectionActionSP);
    IUSaveConfigNumber(fp, &DriftThresholdNP);
    IUSaveConfigNumber(fp, &MaxSyncDriftNP);
    IUSaveConfigNumber(fp, &SolveFreshnessMaxAgeNP);
    return true;
}

double PiFinderMountBridge::angularSeparationArcmin(double ra1, double dec1, double ra2, double dec2) const
{
    const double toRad = M_PI / 180.0;
    const double ra1Rad = ra1 * 15.0 * toRad;
    const double dec1Rad = dec1 * toRad;
    const double ra2Rad = ra2 * 15.0 * toRad;
    const double dec2Rad = dec2 * toRad;

    double cosSep = sin(dec1Rad) * sin(dec2Rad) + cos(dec1Rad) * cos(dec2Rad) * cos(ra1Rad - ra2Rad);
    cosSep = std::max(-1.0, std::min(1.0, cosSep));

    return acos(cosSep) / toRad * 60.0;
}
