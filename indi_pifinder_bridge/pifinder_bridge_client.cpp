#include "pifinder_bridge_client.h"

#include <cmath>
#include <cstdio>
#include <ctime>

PiFinderBridgeClient::PiFinderBridgeClient()
{
}

void PiFinderBridgeClient::setDevices(const std::string &piFinderName, const std::string &mountName)
{
    m_piFinderName = piFinderName;
    m_mountName = mountName;
    m_piFinderOnline = m_mountOnline = false;
    m_piFinderEqNP = m_mountEqNP = nullptr;
    m_piFinderTargetNP = nullptr;
    m_mountOnCoordSetSP = nullptr;
    m_mountMountTypeSP = nullptr;
    m_mountAbortSP = nullptr;
    m_mountSlewRateSP = nullptr;

    m_bindingRetryTicksElapsed = 0;
    m_bindingRetryCooldownTicks = 0;
    m_bindingRetryAttempts = 0;
    m_bindingGaveUp = false;

    watchDevice(m_piFinderName.c_str());
    watchDevice(m_mountName.c_str());
}

bool PiFinderBridgeClient::isReady() const
{
    return m_piFinderEqNP != nullptr && m_mountEqNP != nullptr && m_mountOnCoordSetSP != nullptr;
}

bool PiFinderBridgeClient::retryMissingPropertiesIfNeeded()
{
    if (isReady() || m_bindingGaveUp)
        return false;

    ++m_bindingRetryTicksElapsed;

    if (m_bindingRetryTicksElapsed < BINDING_RETRY_GRACE_TICKS)
        return false;

    if (m_bindingRetryCooldownTicks > 0)
    {
        --m_bindingRetryCooldownTicks;
        return false;
    }

    if (m_bindingRetryAttempts >= BINDING_RETRY_MAX_ATTEMPTS)
    {
        m_bindingGaveUp = true;
        return false;
    }

    // Re-request only whichever properties never arrived - watchProperty(),
    // unlike watchDevice(), actually resends <getProperties> on every call,
    // which is exactly what's needed here (a device/property that showed up
    // late gets asked again, one that's genuinely never coming doesn't get
    // silently retried forever without eventually hitting the attempt cap
    // above).
    if (!m_piFinderEqNP)
        watchProperty(m_piFinderName.c_str(), "EQUATORIAL_EOD_COORD");
    if (!m_mountEqNP)
        watchProperty(m_mountName.c_str(), "EQUATORIAL_EOD_COORD");
    if (!m_mountOnCoordSetSP)
        watchProperty(m_mountName.c_str(), "ON_COORD_SET");

    ++m_bindingRetryAttempts;
    m_bindingRetryCooldownTicks = BINDING_RETRY_INTERVAL_TICKS;
    return true;
}

void PiFinderBridgeClient::setShadowDevice(const std::string &shadowName)
{
    if (shadowName == m_shadowName)
        return;

    m_shadowName = shadowName;
    m_shadowOnline = false;
    m_shadowEqNP = nullptr;
    m_shadowOnCoordSetSP = nullptr;

    if (!m_shadowName.empty())
        watchDevice(m_shadowName.c_str());
}

bool PiFinderBridgeClient::isShadowReady() const
{
    return m_shadowEqNP != nullptr && m_shadowOnCoordSetSP != nullptr;
}

bool PiFinderBridgeClient::syncShadowCoords(double ra, double dec)
{
    if (!isShadowReady())
        return false;

    auto syncSwitch = m_shadowOnCoordSetSP->findWidgetByName("SYNC");
    if (syncSwitch == nullptr)
        return false;

    m_shadowOnCoordSetSP->reset();
    syncSwitch->setState(ISS_ON);
    sendNewSwitch(m_shadowOnCoordSetSP);

    m_shadowEqNP->at(0)->setValue(ra);
    m_shadowEqNP->at(1)->setValue(dec);
    m_shadowEqNP->setState(IPS_OK); // Sync is instantaneous, unlike sendMountCoords()'s IPS_BUSY for a real slew
    sendNewNumber(m_shadowEqNP);

    return true;
}

void PiFinderBridgeClient::newDevice(INDI::BaseDevice dp)
{
    if (dp.isDeviceNameMatch(m_piFinderName))
        m_piFinderOnline = true;
    if (dp.isDeviceNameMatch(m_mountName))
        m_mountOnline = true;
    if (!m_shadowName.empty() && dp.isDeviceNameMatch(m_shadowName))
        m_shadowOnline = true;
}

void PiFinderBridgeClient::newProperty(INDI::Property property)
{
    const bool fromPiFinder = m_piFinderName == property.getDeviceName();
    const bool fromMount = m_mountName == property.getDeviceName();
    const bool fromShadow = !m_shadowName.empty() && m_shadowName == property.getDeviceName();

    if (fromMount && property.isNameMatch("EQUATORIAL_EOD_COORD"))
        m_mountEqNP = property.getNumber();
    else if (fromMount && property.isNameMatch("ON_COORD_SET"))
        m_mountOnCoordSetSP = property.getSwitch();
    else if (fromMount && property.isNameMatch("TELESCOPE_MOUNT_TYPE"))
        m_mountMountTypeSP = property.getSwitch();
    else if (fromMount && property.isNameMatch("TELESCOPE_ABORT_MOTION"))
        m_mountAbortSP = property.getSwitch();
    else if (fromMount && property.isNameMatch("TELESCOPE_SLEW_RATE"))
        m_mountSlewRateSP = property.getSwitch();
    else if (fromPiFinder && property.isNameMatch("EQUATORIAL_EOD_COORD"))
        m_piFinderEqNP = property.getNumber();
    else if (fromPiFinder && property.isNameMatch("TARGET_EOD_COORD"))
        m_piFinderTargetNP = property.getNumber();
    else if (fromShadow && property.isNameMatch("EQUATORIAL_EOD_COORD"))
        m_shadowEqNP = property.getNumber();
    else if (fromShadow && property.isNameMatch("ON_COORD_SET"))
        m_shadowOnCoordSetSP = property.getSwitch();
}

void PiFinderBridgeClient::updateProperty(INDI::Property property)
{
    const bool fromMount = m_mountName == property.getDeviceName();
    const bool fromPiFinder = m_piFinderName == property.getDeviceName();

    if (fromMount && property.isNameMatch("EQUATORIAL_EOD_COORD") && property.getState() == IPS_ALERT)
    {
        std::lock_guard<std::mutex> lock(m_mountRejectMutex);
        m_mountRejectedLastCoords = true;
    }
    else if (fromPiFinder && property.isNameMatch("TARGET_EOD_COORD"))
    {
        // Every genuine Goto request on the PiFinder device re-publishes
        // this property (see consumePiFinderTargetPending()'s own comment
        // in the header) - mark it pending regardless of whether the value
        // actually changed from last time.
        std::lock_guard<std::mutex> lock(m_piFinderTargetMutex);
        m_piFinderTargetPending = true;
    }
}

void PiFinderBridgeClient::newMessage(INDI::BaseDevice baseDevice, int messageID)
{
    if (m_mountName != baseDevice.getDeviceName())
        return;

    // messageQueue() returns "<ISO-8601 timestamp>: <text>" - strip the
    // timestamp prefix for GUI display, INDI clients already show one of
    // their own alongside it.
    std::string msg = baseDevice.messageQueue(messageID);
    const auto sep = msg.find(": ");
    if (sep != std::string::npos)
        msg = msg.substr(sep + 2);

    std::lock_guard<std::mutex> lock(m_mountRejectMutex);
    m_mountRejectMessage = msg;
}

void PiFinderBridgeClient::removeProperty(INDI::Property property)
{
    if (property.getNumber() == m_piFinderEqNP)
        m_piFinderEqNP = nullptr;
    else if (property.getNumber() == m_piFinderTargetNP)
        m_piFinderTargetNP = nullptr;
    else if (property.getNumber() == m_mountEqNP)
        m_mountEqNP = nullptr;
    else if (property.getSwitch() == m_mountOnCoordSetSP)
        m_mountOnCoordSetSP = nullptr;
    else if (property.getSwitch() == m_mountMountTypeSP)
        m_mountMountTypeSP = nullptr;
    else if (property.getSwitch() == m_mountAbortSP)
        m_mountAbortSP = nullptr;
    else if (property.getSwitch() == m_mountSlewRateSP)
        m_mountSlewRateSP = nullptr;
    else if (property.getNumber() == m_shadowEqNP)
        m_shadowEqNP = nullptr;
    else if (property.getSwitch() == m_shadowOnCoordSetSP)
        m_shadowOnCoordSetSP = nullptr;
}

// See the header comment on m_lastBadCoordWarnTime for the incident this
// guards against. `ra`/`dec` are only used for the rate-limited warning
// message here - the actual accept/reject decision is the same finite +
// Dec-in-[-90,90] check used by indi_pifinder_simulator's own
// isUsableCoordinate(), duplicated rather than shared across the two
// separate driver binaries (same "standalone build, no shared library
// between drivers" pattern this project already uses throughout).
bool PiFinderBridgeClient::isUsableCoordinateForWarn(const char *sourceLabel, double ra, double dec) const
{
    if (std::isfinite(ra) && std::isfinite(dec) && dec >= -90.0 && dec <= 90.0)
        return true;

    const long now = static_cast<long>(time(nullptr));
    if (now - m_lastBadCoordWarnTime >= BAD_COORD_WARN_INTERVAL_SEC)
    {
        m_lastBadCoordWarnTime = now;
        fprintf(stderr, "PiFinderBridgeClient: rejecting unusable %s coordinate (RA %.4fh DEC %.4f - "
                "not finite or Dec out of [-90,90]); treating as no-data-yet.\n",
                sourceLabel, ra, dec);
        fflush(stderr);
    }
    return false;
}

bool PiFinderBridgeClient::getPiFinderRADE(double &ra, double &dec) const
{
    if (m_piFinderEqNP == nullptr)
        return false;

    ra = m_piFinderEqNP->at(0)->getValue();
    dec = m_piFinderEqNP->at(1)->getValue();
    return isUsableCoordinateForWarn("PiFinder", ra, dec);
}

bool PiFinderBridgeClient::getMountRADE(double &ra, double &dec) const
{
    if (m_mountEqNP == nullptr)
        return false;

    ra = m_mountEqNP->at(0)->getValue();
    dec = m_mountEqNP->at(1)->getValue();
    return isUsableCoordinateForWarn("mount", ra, dec);
}

bool PiFinderBridgeClient::getPiFinderTargetRADE(double &ra, double &dec) const
{
    if (m_piFinderTargetNP == nullptr)
        return false;

    ra = m_piFinderTargetNP->at(0)->getValue();
    dec = m_piFinderTargetNP->at(1)->getValue();
    return isUsableCoordinateForWarn("PiFinder target", ra, dec);
}

bool PiFinderBridgeClient::consumePiFinderTargetPending()
{
    std::lock_guard<std::mutex> lock(m_piFinderTargetMutex);
    const bool wasPending = m_piFinderTargetPending;
    m_piFinderTargetPending = false;
    return wasPending;
}

bool PiFinderBridgeClient::isMountSlewing() const
{
    return m_mountEqNP != nullptr && m_mountEqNP->getState() == IPS_BUSY;
}

bool PiFinderBridgeClient::getMountType(std::string &outType) const
{
    if (m_mountMountTypeSP == nullptr)
        return false;

    // Read by index, not by switch-item name: INDI::Telescope's own enum
    // (inditelescope.h) fixes the order MOUNT_ALTAZ=0, MOUNT_EQ_FORK=1,
    // MOUNT_EQ_GEM=2 for every driver derived from it - more robust than
    // guessing the exact item-name strings a given driver used.
    const int onIndex = m_mountMountTypeSP->findOnSwitchIndex();
    if (onIndex == 0)
        outType = "Alt/Az";
    else if (onIndex == 1 || onIndex == 2)
        outType = "EQ";
    else
        return false;

    return true;
}

int PiFinderBridgeClient::getSlewRateCount() const
{
    return m_mountSlewRateSP == nullptr ? 0 : static_cast<int>(m_mountSlewRateSP->count());
}

bool PiFinderBridgeClient::setSlewRateIndex(int index)
{
    if (m_mountSlewRateSP == nullptr || index < 0 || index >= static_cast<int>(m_mountSlewRateSP->count()))
        return false;

    auto rateSwitch = m_mountSlewRateSP->at(index);
    if (rateSwitch->getState() == ISS_ON)
        return true; // already selected - avoid redundant INDI traffic every tick

    m_mountSlewRateSP->reset();
    rateSwitch->setState(ISS_ON);
    sendNewSwitch(m_mountSlewRateSP);
    return true;
}

bool PiFinderBridgeClient::sendMountCoords(double ra, double dec, const char *coordSetName)
{
    if (!isReady())
        return false;

    auto coordSetSwitch = m_mountOnCoordSetSP->findWidgetByName(coordSetName);
    if (coordSetSwitch == nullptr)
        return false;

    {
        std::lock_guard<std::mutex> lock(m_mountRejectMutex);
        m_mountRejectedLastCoords = false;
        m_mountRejectMessage.clear();
    }

    m_mountOnCoordSetSP->reset();
    coordSetSwitch->setState(ISS_ON);
    sendNewSwitch(m_mountOnCoordSetSP);

    m_mountEqNP->at(0)->setValue(ra);
    m_mountEqNP->at(1)->setValue(dec);
    m_mountEqNP->setState(IPS_BUSY);
    sendNewNumber(m_mountEqNP);

    m_lastMountCommandTime = static_cast<long>(time(nullptr));

    return true;
}

double PiFinderBridgeClient::secondsSinceLastMountCommand() const
{
    if (m_lastMountCommandTime == 0)
        return 1e9;
    return static_cast<double>(static_cast<long>(time(nullptr)) - m_lastMountCommandTime);
}

bool PiFinderBridgeClient::mountRejectedLastCoords(std::string &outMessage)
{
    std::lock_guard<std::mutex> lock(m_mountRejectMutex);

    if (!m_mountRejectedLastCoords)
        return false;

    outMessage = m_mountRejectMessage;
    m_mountRejectedLastCoords = false;
    return true;
}

bool PiFinderBridgeClient::abortMount()
{
    if (m_mountAbortSP == nullptr)
        return false;

    // Single-switch property on every INDI::Telescope - by position, not
    // name, same reasoning as getMountType() above.
    m_mountAbortSP->reset();
    m_mountAbortSP->at(0)->setState(ISS_ON);
    sendNewSwitch(m_mountAbortSP);

    return true;
}
