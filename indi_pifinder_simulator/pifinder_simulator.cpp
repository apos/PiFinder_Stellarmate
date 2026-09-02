#include "pifinder_simulator.h"

#include <cmath>
#include <cstring>
#include <ctime>
#include <string>

#include <curl/curl.h>
#include <nlohmann/json.hpp>

namespace
{

size_t appendToString(char *ptr, size_t size, size_t nmemb, void *userdata)
{
    static_cast<std::string *>(userdata)->append(ptr, size * nmemb);
    return size * nmemb;
}

// Found live (2026-09-01): this device's position used to default to a
// fixed, compiled-in RA/Dec (5.5h/20 deg) regardless of actual time/location
// - on a real mount, Connect()ing and then Goto-Forward syncing to that
// default could send the OTA below the horizon, risking the mount or the
// scope. Mount Bridge's own Multi-Point Alignment already solves exactly
// this via PiFinder's /api/nearby_bright_stars (altitude-filtered
// server-side using PiFinder's own GPS location/time - see
// httpGetNearbyBrightStars() in pifinder_mount_bridge.cpp and
// docs/concepts/mount_bridge_multistar_alignment.md §4.2) - reused here
// rather than inventing a second altitude-safety mechanism. Returns false
// (leaving the caller's own fallback in place) if PiFinder's web server
// isn't reachable yet or has no candidate above minAltitude.
bool pickSafeDefaultPosition(double minAltitude, double &outRA, double &outDec, std::string &outName)
{
    for (const char *url : {"http://127.0.0.1/api/nearby_bright_stars", "http://127.0.0.1:8080/api/nearby_bright_stars"})
    {
        CURL *curl = curl_easy_init();
        if (curl == nullptr)
            continue;

        char fullUrl[192];
        std::snprintf(fullUrl, sizeof(fullUrl), "%s?radius=180&count=1&min_altitude=%.1f", url, minAltitude);

        std::string body;
        curl_easy_setopt(curl, CURLOPT_URL, fullUrl);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, appendToString);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &body);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, 3000L);
        curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);

        const CURLcode res = curl_easy_perform(curl);
        long httpCode = 0;
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpCode);
        curl_easy_cleanup(curl);

        if (res != CURLE_OK || httpCode != 200)
            continue;

        try
        {
            const auto parsed = nlohmann::json::parse(body);
            const auto &candidates = parsed.at("candidates");
            if (candidates.empty())
                continue;
            const auto &c = candidates.front();
            outRA = c.at("ra").get<double>() / 15.0;
            outDec = c.at("dec").get<double>();
            outName = c.value("name", std::string("?"));
            return true;
        }
        catch (const nlohmann::json::exception &)
        {
            continue;
        }
    }
    return false;
}

} // namespace

static std::unique_ptr<PiFinderSimulator> pifinder_simulator(new PiFinderSimulator());

PiFinderSimulator::PiFinderSimulator()
{
    setVersion(1, 0);
    SetTelescopeCapability(TELESCOPE_CAN_GOTO | TELESCOPE_CAN_SYNC | TELESCOPE_CAN_ABORT, 1);

    // Matches what Goto()/Sync() already set - this device has a real,
    // usable position from construction (see m_hasPosition's header
    // comment), so its TrackState should say so from the start too, not
    // just after the first client command.
    TrackState = SCOPE_TRACKING;
}

const char *PiFinderSimulator::getDefaultName()
{
    return "PiFinder Simulator";
}

bool PiFinderSimulator::initProperties()
{
    INDI::Telescope::initProperties();

    // No physical link of any kind - this is a pure in-memory value holder,
    // nothing to open a serial/TCP connection to.
    setTelescopeConnection(CONNECTION_NONE);

    SetParkDataType(PARK_NONE);

    addAuxControls();

    PushToTargetNP[0].fill("RA", "RA (h)", "%.6f", 0, 24, 0, 0);
    PushToTargetNP[1].fill("DEC", "DEC (deg)", "%.6f", -90, 90, 0, 0);
    PushToTargetNP.fill(getDeviceName(), "SIMULATE_PUSH_TO", "Simulate push-to", MAIN_CONTROL_TAB, IP_RW, 60, IPS_IDLE);

    // §9, docs/concepts/complete_position_simulator.md - see ISSnoopDevice()'s
    // own comment. Empty by default (following off) - never hardcoded.
    IUFillText(&MountDeviceT[MOUNT_DEVICE], "MOUNT_DEVICE", "Follow mount while slewing", "");
    IUFillTextVector(&MountDeviceTP, MountDeviceT, 1, getDeviceName(), "FOLLOW_MOUNT_DEVICE",
                      "Follow mount", "Main Control", IP_RW, 60, IPS_IDLE);

    // Snoop decode target - name/element names must match the real
    // EQUATORIAL_EOD_COORD shape for IUSnoopNumber() to recognize it.
    // "device" filled in once a mount is actually named (see ISNewText()).
    IUFillNumber(&MountEqN[MOUNT_AXIS_RA], "RA", "RA", "%.6f", 0, 24, 0, 0);
    IUFillNumber(&MountEqN[MOUNT_AXIS_DE], "DEC", "DEC", "%.6f", -90, 90, 0, 0);
    IUFillNumberVector(&MountEqNP, MountEqN, 2, "", "EQUATORIAL_EOD_COORD", "Eq. Coordinates",
                        "Main Control", IP_RO, 60, IPS_IDLE);

    // Second snoop decode target on the same mount device: its slew target
    // (see the header comment on MountTargetNP - used to tell a genuine new
    // forwarded GoTo apart from a HOLDING re-sync). "device" filled in
    // alongside MountEqNP in ISNewText().
    IUFillNumber(&MountTargetN[MOUNT_TGT_RA], "RA", "RA", "%.6f", 0, 24, 0, 0);
    IUFillNumber(&MountTargetN[MOUNT_TGT_DE], "DEC", "DEC", "%.6f", -90, 90, 0, 0);
    IUFillNumberVector(&MountTargetNP, MountTargetN, 2, "", "TARGET_EOD_COORD", "Slew Target",
                        "Main Control", IP_RO, 60, IPS_IDLE);

    // Fixed, singular device (see the header comment) - snoop registration
    // never needs to change, so it happens once here rather than through
    // ISNewText() like MountDeviceTP above.
    IUFillNumber(&MountBridgeCorrectionAgeN[0], "AGE_SEC", "Mount Bridge correction age", "%.0f", 0, 1e9, 0, 1e9);
    IUFillNumberVector(&MountBridgeCorrectionAgeNP, MountBridgeCorrectionAgeN, 1, MOUNT_BRIDGE_DEVICE_NAME,
                        "CORRECTION_AGE", "Correction age", "Main Control", IP_RO, 60, IPS_IDLE);
    IDSnoopDevice(MOUNT_BRIDGE_DEVICE_NAME, "CORRECTION_AGE");

    // Base class already defaults EQUATORIAL_EOD_COORD to IPS_OK on
    // construction, which is what we want here (see m_hasPosition's own
    // comment, 2026-09-01: this device starts with a real, usable
    // above-the-horizon position, not an empty one) - no override needed.

    return true;
}

bool PiFinderSimulator::updateProperties()
{
    INDI::Telescope::updateProperties();

    if (isConnected())
    {
        defineProperty(PushToTargetNP);
        defineProperty(&MountDeviceTP);

        // See m_connectedConfigLoaded's own comment - MountDeviceTP has
        // nothing to load into until just now. loadConfig() re-delivers any
        // saved value through our own ISNewText() (same "config replay"
        // mechanism pifinder_mount_bridge.cpp's ActiveDeviceTP already
        // relies on - see its own comment), which is what actually performs
        // the IDSnoopDevice() registration - no separate call needed here.
        if (!m_connectedConfigLoaded)
        {
            loadConfig(true, MountDeviceTP.name);
            m_connectedConfigLoaded = true;
        }
    }
    else
    {
        deleteProperty(PushToTargetNP);
        deleteProperty(MountDeviceTP.name);
    }

    return true;
}

bool PiFinderSimulator::saveConfigItems(FILE *fp)
{
    INDI::Telescope::saveConfigItems(fp);
    IUSaveConfigText(fp, &MountDeviceTP);
    return true;
}

bool PiFinderSimulator::Connect()
{
    LOG_INFO("PiFinder Simulator connected.");
    // Runs exactly once per process lifetime, before any client could
    // realistically have issued a Sync()/Goto() yet (those need this
    // Connect() to have already succeeded) - see pickSafeDefaultPosition()'s
    // own comment for why the compiled-in default alone isn't safe.
    if (!m_startupDefaultReplaced)
    {
        double safeRA, safeDec;
        std::string safeName;
        if (pickSafeDefaultPosition(20.0, safeRA, safeDec, safeName))
        {
            m_currentRA = safeRA;
            m_currentDEC = safeDec;
            LOGF_INFO("Defaulting to a real, currently-visible star (%s, RA %.4fh, DEC %.4f deg) instead of the fixed compiled-in default.",
                      safeName.c_str(), safeRA, safeDec);
        }
        else
        {
            LOG_WARN("Could not fetch a safe default position from PiFinder's own /api/nearby_bright_stars (not reachable yet?) - keeping the compiled-in default. Sync/Goto to a real target before relying on this device's position.");
        }
        m_startupDefaultReplaced = true;
    }
    // Found live (2026-09-01): nothing ever started the poll loop on
    // Connect() - TimerHit()/ReadScopeStatus() genuinely never ran even
    // once without this (confirmed with a throwaway counter property, not
    // just inference), no matter what m_hasPosition/TrackState defaulted
    // to. Sync()/Goto() worked regardless since they're plain client-
    // triggered calls, independent of polling - that's what made this
    // driver look like it "worked" all along. Same pattern already used by
    // pifinder_mount_bridge.cpp's own Connect().
    SetTimer(getCurrentPollingPeriod());
    return true;
}

bool PiFinderSimulator::Disconnect()
{
    LOG_INFO("PiFinder Simulator disconnected.");
    return true;
}

void PiFinderSimulator::TimerHit()
{
    if (!isConnected())
        return;
    ReadScopeStatus();
    SetTimer(getCurrentPollingPeriod());
}

bool PiFinderSimulator::ReadScopeStatus()
{
    // Deliberately never changes on its own between Sync()/Goto() calls -
    // see the header comment: this device holds still exactly where it was
    // put (starting at its own fixed above-the-horizon default, see
    // m_hasPosition's header comment), so a test session always knows
    // precisely what "sky truth" it's currently feeding PiFinder.
    //
    // m_hasPosition is always true from construction now, but the guard
    // stays (cheap, and self-documenting) rather than assuming so silently.
    //
    // Force IPS_OK on every poll, not just once inside Goto()/
    // Sync() - found live: the base class's own TRACK-mode dispatch resets
    // EqNP back to IPS_BUSY right after Goto() returns (normal "still
    // slewing" convention for a real telescope), overriding an IPS_OK set
    // from inside Goto() itself. This device has no simulated slew time
    // (see the class comment) - it always "arrives" instantly, so every
    // tick after the first should show OK, not stay stuck on Busy forever.
    if (m_hasPosition)
    {
        NewRaDec(m_currentRA, m_currentDEC);
        if (EqNP.getState() != IPS_OK)
        {
            EqNP.setState(IPS_OK);
            EqNP.apply();
        }
    }
    return true;
}

bool PiFinderSimulator::Goto(double ra, double dec)
{
    // No simulated slew time - takes effect immediately, same as Sync().
    // A real slew delay isn't useful here: the point of this device is a
    // precisely known, immediately-settable position, not motion realism
    // (the real Telescope Simulator already covers that for the mount side).
    m_currentRA = ra;
    m_currentDEC = dec;
    m_hasPosition = true;
    TrackState = SCOPE_TRACKING;
    LOGF_INFO("Goto: RA %.4fh, DEC %.4f deg.", ra, dec);
    // Found live (2026-08-30): the base class's own dispatch already marks
    // EqNP IPS_BUSY before calling Goto() (normal "slewing" convention), and
    // NewRaDec() only updates the value, not the state - left uncorrected,
    // it stayed stuck on Busy forever, since this driver has no simulated
    // slew time to eventually finish. Set OK explicitly: this device always
    // "arrives" the instant Goto()/Sync() is called (see the class comment).
    NewRaDec(m_currentRA, m_currentDEC);
    EqNP.setState(IPS_OK);
    EqNP.apply();
    return true;
}

bool PiFinderSimulator::Sync(double ra, double dec)
{
    m_currentRA = ra;
    m_currentDEC = dec;
    m_hasPosition = true;
    TrackState = SCOPE_TRACKING;
    LOGF_INFO("Sync: RA %.4fh, DEC %.4f deg.", ra, dec);
    NewRaDec(m_currentRA, m_currentDEC);
    EqNP.setState(IPS_OK);
    EqNP.apply();
    return true;
}

bool PiFinderSimulator::ISNewNumber(const char *dev, const char *name, double values[], char *names[], int n)
{
    if (dev != nullptr && !strcmp(dev, getDeviceName()) && !strcmp(name, PushToTargetNP.getName()))
    {
        PushToTargetNP.update(values, names, n);
        PushToTargetNP.setState(IPS_OK);
        PushToTargetNP.apply();

        // Deliberately only touches TargetNP (TARGET_EOD_COORD), not
        // m_currentRA/DEC - see the header comment on PushToTargetNP. A real
        // push-to doesn't change PiFinder's own reported position either.
        TargetNP[0].setValue(PushToTargetNP[0].getValue());
        TargetNP[1].setValue(PushToTargetNP[1].getValue());
        TargetNP.setState(IPS_OK);
        TargetNP.apply();

        LOGF_INFO("Simulated PiFinder push-to: RA %.4fh, DEC %.4f deg (TARGET_EOD_COORD updated, "
                  "current position left unchanged).",
                  PushToTargetNP[0].getValue(), PushToTargetNP[1].getValue());
        return true;
    }

    return INDI::Telescope::ISNewNumber(dev, name, values, names, n);
}

bool PiFinderSimulator::ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n)
{
    if (dev != nullptr && !strcmp(dev, getDeviceName()) && !strcmp(name, MountDeviceTP.name))
    {
        IUUpdateText(&MountDeviceTP, texts, names, n);
        MountDeviceTP.s = IPS_OK;
        IDSetText(&MountDeviceTP, nullptr);

        const std::string newDevice = MountDeviceT[MOUNT_DEVICE].text ? MountDeviceT[MOUNT_DEVICE].text : "";
        if (newDevice != m_snoopedMountDevice)
        {
            m_snoopedMountDevice = newDevice;
            strncpy(MountEqNP.device, newDevice.c_str(), MAXINDIDEVICE - 1);
            MountEqNP.device[MAXINDIDEVICE - 1] = '\0';
            strncpy(MountTargetNP.device, newDevice.c_str(), MAXINDIDEVICE - 1);
            MountTargetNP.device[MAXINDIDEVICE - 1] = '\0';
            m_haveLastMountTarget = false;
            m_followActive = false;
            // See ISSnoopDevice()'s own comment - re-registering is harmless
            // (indiserver just keeps the latest registration for this
            // property/device pair); an empty name effectively means
            // "nothing named yet", not "watch nothing" - indiserver simply
            // never sees a device with an empty name, so no snoop events
            // arrive, same net effect.
            if (!newDevice.empty())
            {
                IDSnoopDevice(newDevice.c_str(), "EQUATORIAL_EOD_COORD");
                IDSnoopDevice(newDevice.c_str(), "TARGET_EOD_COORD");
            }
            LOGF_INFO("Following mount device for real slews: %s", newDevice.empty() ? "(none)" : newDevice.c_str());
            // Persist across restarts - see m_connectedConfigLoaded's own
            // comment for why this was missing before (found live 2026-09-01,
            // "Full Sim / Goto mount -> Dead reckoning geht nicht": a fresh
            // profile restart silently reset this back to empty/off).
            saveConfig(true, MountDeviceTP.name);
        }
        return true;
    }

    return INDI::Telescope::ISNewText(dev, name, texts, names, n);
}

bool PiFinderSimulator::ISSnoopDevice(XMLEle *root)
{
    const char *deviceName = findXMLAttValu(root, "device");

    if (deviceName && strcmp(deviceName, MOUNT_BRIDGE_DEVICE_NAME) == 0)
    {
        if (IUSnoopNumber(root, &MountBridgeCorrectionAgeNP) == 0)
            m_mountBridgeCorrectionAge = MountBridgeCorrectionAgeN[0].value;
        return true;
    }

    if (deviceName && !m_snoopedMountDevice.empty() && m_snoopedMountDevice == deviceName)
    {
        // The mount's slew target changed -> a genuine new GoTo to a new
        // place is starting. Follow the mount through to it, regardless of
        // Mount Bridge's CORRECTION_AGE (a forwarded user GoTo goes out via
        // sendMountCoords() too, so the age can't tell it apart from a
        // correction - the target change can). A HOLDING re-sync re-issues
        // the *same* target, so TARGET_EOD_COORD does not change and this
        // does not trip.
        if (IUSnoopNumber(root, &MountTargetNP) == 0)
        {
            const double tgtRA = MountTargetN[MOUNT_TGT_RA].value;
            const double tgtDEC = MountTargetN[MOUNT_TGT_DE].value;
            const bool changed = !m_haveLastMountTarget ||
                                 separationArcmin(m_lastMountTargetRA, m_lastMountTargetDEC, tgtRA, tgtDEC)
                                     > MOUNT_TARGET_CHANGE_EPS_DEG * 60.0;
            if (m_haveLastMountTarget && changed)
            {
                m_followActive = true;
                m_followTargetRA = tgtRA;
                m_followTargetDEC = tgtDEC;
                m_followDeadline = static_cast<long>(time(nullptr)) + FOLLOW_TIMEOUT_SEC;
                LOGF_INFO("Mount slew target changed (RA %.4fh DEC %.4f) - following it through the slew.",
                          tgtRA, tgtDEC);
            }
            m_lastMountTargetRA = tgtRA;
            m_lastMountTargetDEC = tgtDEC;
            m_haveLastMountTarget = true;
            return true;
        }

        if (IUSnoopNumber(root, &MountEqNP) == 0)
        {
            // PiFinder is rigidly attached to the OTA, so a real slew moves
            // it too - but ordinary mount-model drift once the mount is back
            // to idle/tracking must NOT keep dragging this device along, or
            // there is nothing left for Verify/Alert or Auto-correct to
            // detect. Two things get followed:
            //   1. m_followActive - a forwarded new GoTo (target changed
            //      above); follow the mount verbatim until it settles on the
            //      new target (or a safety timeout).
            //   2. a Busy episode NOT explained by Mount Bridge itself
            //      (CORRECTION_AGE old) - e.g. a hand-paddle / external slew.
            // Mount Bridge's own small HOLDING/auto-correct re-syncs match
            // neither (same target, fresh CORRECTION_AGE) and stay unfollowed
            // - the feedback loop that used to walk PiFinder and mount off
            // together (2026-09-01) does not form.
            if (m_followActive && static_cast<long>(time(nullptr)) > m_followDeadline)
            {
                m_followActive = false;
                LOG_INFO("Mount-follow timed out (mount never settled on the new target) - holding here.");
            }

            const bool externalSlew = MountEqNP.s == IPS_BUSY &&
                                      m_mountBridgeCorrectionAge >= CORRECTION_GRACE_SEC;

            if (m_followActive || externalSlew)
            {
                m_currentRA = MountEqN[MOUNT_AXIS_RA].value;
                m_currentDEC = MountEqN[MOUNT_AXIS_DE].value;
                m_hasPosition = true;
                TrackState = SCOPE_TRACKING;
                NewRaDec(m_currentRA, m_currentDEC);
                if (EqNP.getState() != IPS_OK)
                {
                    EqNP.setState(IPS_OK);
                    EqNP.apply();
                }
            }

            // Stop following once the mount has settled (state OK) close to
            // the new target - the exact settled position was just copied
            // above, so this device ends up precisely where the mount is.
            if (m_followActive && MountEqNP.s == IPS_OK &&
                separationArcmin(m_currentRA, m_currentDEC, m_followTargetRA, m_followTargetDEC)
                    < FOLLOW_ARRIVED_ARCMIN)
            {
                m_followActive = false;
            }
        }
        return true;
    }

    return INDI::Telescope::ISSnoopDevice(root);
}

double PiFinderSimulator::separationArcmin(double ra1_h, double dec1_d, double ra2_h, double dec2_d)
{
    const double d2r = M_PI / 180.0;
    const double ra1 = ra1_h * 15.0 * d2r, ra2 = ra2_h * 15.0 * d2r;
    const double dec1 = dec1_d * d2r, dec2 = dec2_d * d2r;
    double c = std::sin(dec1) * std::sin(dec2) + std::cos(dec1) * std::cos(dec2) * std::cos(ra1 - ra2);
    c = std::max(-1.0, std::min(1.0, c));
    return std::acos(c) / d2r * 60.0;
}
