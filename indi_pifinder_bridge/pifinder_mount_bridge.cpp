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

    IUFillNumber(&DriftThresholdN[0], "THRESHOLD_ARCMIN", "Threshold (arcmin)", "%.1f", 0.1, 600, 0.5, 5);
    IUFillNumberVector(&DriftThresholdNP, DriftThresholdN, 1, getDeviceName(), "DRIFT_THRESHOLD",
                       "Drift Threshold", "Main Control", IP_RW, 60, IPS_IDLE);

    IUFillNumber(&SolveFreshnessMaxAgeN[0], "MAX_AGE_SEC", "Max solve age (s)", "%.1f", 0.5, 60, 0.5, 5);
    IUFillNumberVector(&SolveFreshnessMaxAgeNP, SolveFreshnessMaxAgeN, 1, getDeviceName(), "SOLVE_FRESHNESS",
                       "Auto-correct solve freshness", "Main Control", IP_RW, 60, IPS_IDLE);

    IUFillNumber(&DriftStatusN[0], "DRIFT_ARCMIN", "Current drift (arcmin)", "%.2f", 0, 10000, 0, 0);
    IUFillNumberVector(&DriftStatusNP, DriftStatusN, 1, getDeviceName(), "DRIFT_STATUS", "Status",
                       "Main Control", IP_RO, 60, IPS_IDLE);

    addDebugControl();
    setDefaultPollingPeriod(2000);

    return true;
}

void PiFinderMountBridge::ISGetProperties(const char *dev)
{
    DefaultDevice::ISGetProperties(dev);

    defineProperty(&SettingsTP);
    defineProperty(&ActiveDeviceTP);

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
        defineProperty(&DriftThresholdNP);
        defineProperty(&SolveFreshnessMaxAgeNP);
        defineProperty(&DriftStatusNP);

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
        deleteProperty(DriftThresholdNP.name);
        deleteProperty(SolveFreshnessMaxAgeNP.name);
        deleteProperty(DriftStatusNP.name);
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

void PiFinderMountBridge::TimerHit()
{
    if (!isConnected())
        return;

    syncMountTypeToPiFinder();

    if (!m_client->isReady())
    {
        SetTimer(getCurrentPollingPeriod());
        return;
    }

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

    if (BridgeModeS[MODE_GOTO_FORWARD].s == ISS_ON)
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

            if (std::isnan(m_lastForwardedRA))
            {
                // First observation since entering this mode - establish a
                // baseline without forwarding, so switching into Goto-Forward
                // doesn't immediately re-send whatever push-to target
                // happened to already be set on PiFinder.
                m_lastForwardedRA = targetRA;
                m_lastForwardedDec = targetDec;
                return;
            }

            const bool isNewTarget = std::abs(targetRA - m_lastForwardedRA) > 1e-9 ||
                                      std::abs(targetDec - m_lastForwardedDec) > 1e-9;
            if (!isNewTarget)
                return;

            if (m_client->sendMountCoords(targetRA, targetDec, "TRACK"))
            {
                LOGF_INFO("New PiFinder target (RA %.4fh, DEC %.4f deg) - forwarded Goto to mount.",
                          targetRA, targetDec);
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
                    LOG_WARN("Gave up waiting for a fresh PiFinder solve after arrival - skipping this settle attempt.");
                    m_forwardState = ForwardState::IDLE;
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

            if (drift > threshold && m_settleRetriesRemaining > 0)
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
                    LOGF_WARN("Gave up refining after %d attempt(s): residual %.1f arcmin still exceeds threshold %.1f.",
                              MAX_SETTLE_RETRIES, drift, threshold);
                else
                    LOGF_INFO("Arrival verified by PiFinder solve: residual %.1f arcmin, within threshold %.1f.",
                              drift, threshold);
                m_forwardState = ForwardState::IDLE;
            }
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
            if (m_client->sendMountCoords(piRA, piDec, "TRACK"))
            {
                LOGF_INFO("Drift %.1f arcmin exceeded threshold - sent Goto to mount.", drift);
                m_correctTargetRA = piRA;
                m_correctTargetDec = piDec;
                m_correctSettleRetriesRemaining = MAX_SETTLE_RETRIES;
                m_correctState = CorrectState::SLEWING;
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
            if (drift > threshold && m_correctSettleRetriesRemaining > 0)
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
                    LOGF_INFO("Auto-correct arrival verified by PiFinder solve: residual %.1f arcmin, within threshold %.1f.",
                              drift, threshold);
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
            m_forwardState = ForwardState::IDLE;
            m_lastForwardedRA = std::nan("");
            m_lastForwardedDec = std::nan("");

            // Same idea for Auto-Correct's Goto-refine state machine - don't
            // let an in-progress settle/retry cycle from a previous mode
            // silently keep running (or resume stale) after switching away
            // and back.
            m_correctState = CorrectState::IDLE;

            // Persist so the chosen mode actually survives a reconnect -
            // see m_connectedConfigLoaded's comment. Without this, the
            // saved config just keeps replaying whatever was last actively
            // saved (typically Off/Verify-Alert from ages ago) regardless
            // of what the user picks live, same "selection doesn't stick"
            // shape as #158's ACTIVE_DEVICES bug.
            saveConfig(true, BridgeModeSP.name);
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
            return true;
        }

        if (strcmp(name, SolveFreshnessMaxAgeNP.name) == 0)
        {
            IUUpdateNumber(&SolveFreshnessMaxAgeNP, values, names, n);
            SolveFreshnessMaxAgeNP.s = IPS_OK;
            IDSetNumber(&SolveFreshnessMaxAgeNP, nullptr);
            return true;
        }
    }

    return DefaultDevice::ISNewNumber(dev, name, values, names, n);
}

bool PiFinderMountBridge::saveConfigItems(FILE *fp)
{
    IUSaveConfigText(fp, &SettingsTP);
    IUSaveConfigText(fp, &ActiveDeviceTP);
    IUSaveConfigSwitch(fp, &BridgeModeSP);
    IUSaveConfigSwitch(fp, &CorrectionActionSP);
    IUSaveConfigNumber(fp, &DriftThresholdNP);
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
