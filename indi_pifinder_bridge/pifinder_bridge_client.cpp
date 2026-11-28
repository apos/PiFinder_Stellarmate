#include "pifinder_bridge_client.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <ctime>

PiFinderBridgeClient::PiFinderBridgeClient()
{
}

void PiFinderBridgeClient::setDevices(const std::string &piFinderName, const std::string &mountName)
{
    m_piFinderName = piFinderName;
    m_mountName = mountName;
    forgetProperties();

    m_bindingRetryTicksElapsed = 0;
    m_bindingRetryCooldownTicks = 0;
    m_bindingRetryAttempts = 0;
    m_bindingGaveUp = false;

    watchAllDevices();
}

// Registered WITH a callback on purpose: on a reconnect libindi asks only for the devices it has an entry for, and an entry is
// made either by this form or by a definition received before. With the plain watchDevice(name), a mount that was not there at
// the first connection was never asked for again - the Bridge stayed blind until its process was restarted (found 2026-11-27,
// profile switch; the same for a mount selected later, #662). A removed device loses its entry, so this is repeated before
// every connect.
void PiFinderBridgeClient::watchAllDevices()
{
    for (const std::string *name : { &m_piFinderName, &m_mountName, &m_shadowName })
        if (!name->empty())
            watchDevice(name->c_str(), [](INDI::BaseDevice) {});
}

// Every pointer into a device is dropped (it is dead once the connection or the device name changes); a target that is on the PiFinder
// device when the properties come back is the baseline, not a new push-to.
void PiFinderBridgeClient::forgetProperties()
{
    m_piFinderOnline = m_mountOnline = false;
    m_piFinderEqNP = m_mountEqNP = nullptr;
    m_piFinderTargetNP = nullptr;
    m_mountOnCoordSetSP = nullptr;
    m_mountMountTypeSP = nullptr;
    m_mountAbortSP = nullptr;
    m_mountSlewRateSP = nullptr;
    // These belonged to the previous mount (or are bound again below); a pointer into a device that is gone must never be read.
    m_mountParkSP = nullptr;
    m_mountGeoNP = nullptr;
    m_mountTargetNP = nullptr;
    m_piFinderGeoNP = nullptr;
    m_mountAddressTP = nullptr;
    m_mountDriverInfoTP = nullptr;
    m_mountConnectionModeSP = nullptr;
    m_mountAlignStarsSP = m_mountAlignSP = m_mountAlignWriteSP = nullptr;
    {
        std::lock_guard<std::mutex> lock(m_alignStatusMutex);
        m_alignStatusKnown = false;
    }
    {
        std::lock_guard<std::mutex> lock(m_restMutex);
        m_parking = m_parked = m_homing = false;
        m_onstepRest = Rest::NONE;
        m_onstepStatusKnown = false;
        m_lastParkOrHomeTime = m_lastIndiMovementTime = 0;
        m_slewStart = m_slewEnd = 0;
        m_slewing = false;
    }
    {
        std::lock_guard<std::mutex> lock(m_piFinderTargetMutex);
        m_piFinderTargetPending = false;   // whatever target is on the PiFinder device now is the baseline, not a new push-to
    }
    {
        std::lock_guard<std::mutex> lock(m_mountEventMutex);
        m_mountEvent = MountEvent::NONE;
        m_ownGotos.clear();
        m_indiGotos.clear();
        m_haveControllerTarget = false;
    }
    m_bindTime = static_cast<long>(time(nullptr));
    m_shadowOnline = false;
    m_shadowEqNP = nullptr;
    m_shadowOnCoordSetSP = nullptr;
}

bool PiFinderBridgeClient::isReady() const
{
    return m_piFinderEqNP != nullptr && m_mountEqNP != nullptr && m_mountOnCoordSetSP != nullptr;
}

bool PiFinderBridgeClient::retryMissingPropertiesIfNeeded()
{
    if (isReady())
    {
        // bound: a later loss of the device starts over with the short budget and its one-time error
        m_bindingRetryTicksElapsed = m_bindingRetryCooldownTicks = m_bindingRetryAttempts = 0;
        m_bindingGaveUp = false;
        return false;
    }

    ++m_bindingRetryTicksElapsed;

    if (m_bindingRetryTicksElapsed < BINDING_RETRY_GRACE_TICKS)
        return false;

    if (m_bindingRetryCooldownTicks > 0)
    {
        --m_bindingRetryCooldownTicks;
        return false;
    }

    // Past the short budget: report it once (bindingGaveUp() drives the one-time error in the driver) but keep asking, slowly.
    const bool longPhase = m_bindingRetryAttempts >= BINDING_RETRY_MAX_ATTEMPTS;
    if (longPhase && !m_bindingGaveUp)
    {
        m_bindingGaveUp = true;
        m_bindingRetryCooldownTicks = BINDING_RETRY_LONG_INTERVAL_TICKS;
        return false;
    }

    // Ask again by connecting anew: that sends <getProperties> for every watched device once more.
    // NEVER watchProperty() here: libindi then drops every OTHER property (and every message) of that device for good
    // (WatchDeviceProperty::processXml, "If we are asked to watch for specific properties only, we ignore everything else"),
    // and a reconnect keeps that filter. Found 2026-11-27: after one retry the Bridge never saw PiFinder's target again and
    // forwarded no GoTo; on the mount side abort, park and location would be filtered the same way.
    disconnectServer();
    forgetProperties();
    watchAllDevices();
    connectServer();

    if (!longPhase)
        ++m_bindingRetryAttempts;
    m_bindingRetryCooldownTicks = longPhase ? BINDING_RETRY_LONG_INTERVAL_TICKS : BINDING_RETRY_INTERVAL_TICKS;
    return !longPhase;   // the slow retries are silent: the one-time error has been logged already
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
        watchAllDevices(); // takes effect for the property requests of the next connect
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
    else if (fromMount && property.isNameMatch("TELESCOPE_PARK"))
    {
        m_mountParkSP = property.getSwitch();
        noteMountRest(property);
    }
    else if (fromMount && property.isNameMatch("TELESCOPE_MOUNT_TYPE"))
        m_mountMountTypeSP = property.getSwitch();
    else if (fromMount && property.isNameMatch("TELESCOPE_ABORT_MOTION"))
        m_mountAbortSP = property.getSwitch();
    else if (fromMount && property.isNameMatch("TELESCOPE_SLEW_RATE"))
        m_mountSlewRateSP = property.getSwitch();
    else if (fromMount && property.isNameMatch("GEOGRAPHIC_COORD"))
        m_mountGeoNP = property.getNumber();
    else if (fromMount && property.isNameMatch("TARGET_EOD_COORD"))
        m_mountTargetNP = property.getNumber();
    else if (fromMount && property.isNameMatch("DEVICE_ADDRESS"))
        m_mountAddressTP = property.getText();
    else if (fromMount && property.isNameMatch("Align Process"))
        noteOnStepAlignStatus(property);
    else if (fromMount && (property.isNameMatch("OnStep Status") || property.isNameMatch("TELESCOPE_HOME")))
        noteMountRest(property);
    else if (fromMount && property.isNameMatch("DRIVER_INFO"))
        m_mountDriverInfoTP = property.getText();
    else if (fromMount && property.isNameMatch("CONNECTION_MODE"))
        m_mountConnectionModeSP = property.getSwitch();
    else if (fromMount && property.isNameMatch("AlignStars"))
        m_mountAlignStarsSP = property.getSwitch();
    else if (fromMount && property.isNameMatch("NewAlignStar"))
        m_mountAlignSP = property.getSwitch();
    else if (fromMount && property.isNameMatch("NewAlignStar2"))
        m_mountAlignWriteSP = property.getSwitch();
    else if (fromPiFinder && property.isNameMatch("GEOGRAPHIC_COORD"))
        m_piFinderGeoNP = property.getNumber();
    else if (fromPiFinder && property.isNameMatch("EQUATORIAL_EOD_COORD"))
        m_piFinderEqNP = property.getNumber();
    else if (fromPiFinder && property.isNameMatch("TARGET_EOD_COORD"))
        m_piFinderTargetNP = property.getNumber();
    else if (fromPiFinder && property.isNameMatch("ON_COORD_SET"))
        m_piFinderOnCoordSetSP = property.getSwitch();
    else if (fromShadow && property.isNameMatch("EQUATORIAL_EOD_COORD"))
        m_shadowEqNP = property.getNumber();
    else if (fromShadow && property.isNameMatch("ON_COORD_SET"))
        m_shadowOnCoordSetSP = property.getSwitch();
}

namespace
{
double separationArcmin(double ra1, double dec1, double ra2, double dec2)
{
    const double toRad = M_PI / 180.0;
    double cosSep = std::sin(dec1 * toRad) * std::sin(dec2 * toRad) +
                    std::cos(dec1 * toRad) * std::cos(dec2 * toRad) * std::cos((ra1 - ra2) * 15.0 * toRad);
    cosSep = std::max(-1.0, std::min(1.0, cosSep));
    return std::acos(cosSep) / toRad * 60.0;
}
}

void PiFinderBridgeClient::rememberIndiGoto(double ra, double dec)
{
    const long now = static_cast<long>(time(nullptr));
    while (!m_indiGotos.empty() && now - m_indiGotos.front().second > INDI_GOTO_MEMORY_SEC)
        m_indiGotos.pop_front();
    m_indiGotos.push_back({ { ra, dec }, now });
}

bool PiFinderBridgeClient::sawIndiGoto(double ra, double dec, double maxAgeSec)
{
    std::lock_guard<std::mutex> lock(m_mountEventMutex);
    const long now = static_cast<long>(time(nullptr));
    for (const auto &seen : m_indiGotos)
    {
        if (now - seen.second <= maxAgeSec && separationArcmin(ra, dec, seen.first.first, seen.first.second) < OWN_GOTO_ECHO_ARCMIN)
            return true;
    }
    return false;
}

void PiFinderBridgeClient::noteControllerGoto(double ra, double dec)
{
    releaseKeptTarget(false, 0.0, 0.0);
    {
        std::lock_guard<std::mutex> lock(m_mountEventMutex);
        m_haveControllerTarget = true;
        m_controllerTargetRA = ra;
        m_controllerTargetDec = dec;
        m_controllerTargetTime = static_cast<long>(time(nullptr));
    }
    noteMountEvent(MountEvent::GOTO, ra, dec);
}

void PiFinderBridgeClient::noteOnStepAlignStatus(INDI::Property property)
{
    auto status = property.getText();
    auto current = status->findWidgetByName("6");
    auto total = status->findWidgetByName("7");
    // "Not Updated" until the driver has read the controller; ":" stands for the tenth value (9 stars finished).
    auto number = [](const char *text, int &value) {
        if (text == nullptr || text[0] < '0' || text[0] > ':' || text[1] != '\0')
            return false;
        value = text[0] - '0';
        return true;
    };
    int star = 0, stars = 0;
    const bool known = current != nullptr && total != nullptr && number(current->getText(), star) && number(total->getText(), stars);
    std::lock_guard<std::mutex> lock(m_alignStatusMutex);
    m_alignStatusKnown = known;
    m_alignStatusStar = star;
    m_alignStatusStars = stars;
}

bool PiFinderBridgeClient::getOnStepAlignStatus(int &star, int &stars) const
{
    std::lock_guard<std::mutex> lock(m_alignStatusMutex);
    star = m_alignStatusStar;
    stars = m_alignStatusStars;
    return m_alignStatusKnown;
}

void PiFinderBridgeClient::noteMountRest(INDI::Property property)
{
    std::lock_guard<std::mutex> lock(m_restMutex);
    const Rest before = restLocked();
    bool firstSight = false; // the first status after binding says where the mount is, not that it just got there
    if (property.isNameMatch("TELESCOPE_PARK"))
    {
        auto park = property.getSwitch()->findWidgetByName("PARK");
        const bool parkOn = park != nullptr && park->getState() == ISS_ON;
        m_parking = parkOn && property.getState() == IPS_BUSY;
        m_parked = parkOn && property.getState() != IPS_BUSY && property.getState() != IPS_ALERT;
    }
    else if (property.isNameMatch("TELESCOPE_HOME"))
    {
        m_homing = property.getState() == IPS_BUSY;
    }
    else
    {
        // ":GU# return" of the INDI OnStep driver: I parking, P parked, h on the way home, H at home.
        auto widget = property.getText()->findWidgetByName(":GU# return");
        const std::string flags = widget != nullptr && widget->getText() != nullptr ? widget->getText() : "";
        firstSight = !m_onstepStatusKnown;
        // A real answer has no blank (the driver shows "Not Updated" before its first one) and always one of the park flags.
        m_onstepStatusKnown = flags.find(' ') == std::string::npos && flags.find_first_of("pPIF") != std::string::npos;
        m_onstepRest = !m_onstepStatusKnown                       ? Rest::NONE
                       : flags.find('I') != std::string::npos     ? Rest::PARKING
                       : flags.find('P') != std::string::npos     ? Rest::PARKED
                       : flags.find('h') != std::string::npos     ? Rest::HOMING
                       : flags.find('H') != std::string::npos     ? Rest::HOME
                                                                  : Rest::NONE;
    }
    restChanged(before, firstSight);
}

PiFinderBridgeClient::Rest PiFinderBridgeClient::restLocked() const
{
    if (m_parking || m_onstepRest == Rest::PARKING)
        return Rest::PARKING;
    if (m_homing || m_onstepRest == Rest::HOMING)
        return Rest::HOMING;
    if (m_parked || m_onstepRest == Rest::PARKED)
        return Rest::PARKED;
    return m_onstepRest;
}

void PiFinderBridgeClient::restChanged(Rest before, bool firstSight)
{
    const Rest now = restLocked();
    if (now == Rest::NONE)
        return;
    m_lastParkOrHomeTime = static_cast<long>(time(nullptr));
    // A movement into park / home: it starts, or it was over before anything but its end was seen. What is already there when the
    // Bridge binds to the mount is no movement.
    const bool moving = now == Rest::PARKING || now == Rest::HOMING;
    const bool wasMoving = before == Rest::PARKING || before == Rest::HOMING;
    if ((moving && !wasMoving) || (!moving && before == Rest::NONE && !firstSight && !justBound()))
        ++m_parkOrHomeStarts;
}

PiFinderBridgeClient::Rest PiFinderBridgeClient::mountRest() const
{
    std::lock_guard<std::mutex> lock(m_restMutex);
    return restLocked();
}

unsigned PiFinderBridgeClient::parkOrHomeStarts() const
{
    std::lock_guard<std::mutex> lock(m_restMutex);
    return m_parkOrHomeStarts;
}

bool PiFinderBridgeClient::isOnStepStatusKnown() const
{
    std::lock_guard<std::mutex> lock(m_restMutex);
    return m_onstepStatusKnown;
}

void PiFinderBridgeClient::noteIndiMovement()
{
    std::lock_guard<std::mutex> lock(m_restMutex);
    m_lastIndiMovementTime = static_cast<long>(time(nullptr));
}

void PiFinderBridgeClient::noteMountMotionState(INDI::Property property)
{
    std::lock_guard<std::mutex> lock(m_restMutex);
    const bool busy = property.getState() == IPS_BUSY;
    const long now = static_cast<long>(time(nullptr));
    if (busy && !m_slewing)
    {
        if (m_slewStart == 0) // a short pause inside one slew does not start a new one
            m_slewStart = now;
    }
    else if (!busy && m_slewing)
        m_slewEnd = now;
    m_slewing = busy;
}

bool PiFinderBridgeClient::takeFinishedSlew(double quietSec, bool &commanded)
{
    const bool bound = justBound();
    const long ownCommand = m_lastMountCommandTime;
    std::lock_guard<std::mutex> lock(m_restMutex);
    if (m_slewing || m_slewStart == 0 || static_cast<double>(static_cast<long>(time(nullptr)) - m_slewEnd) < quietSec)
        return false;
    const long since = m_slewStart - SLEW_COMMAND_MARGIN_SEC;
    commanded = bound || m_lastIndiMovementTime >= since || m_lastParkOrHomeTime >= since || ownCommand >= since;
    m_slewStart = m_slewEnd = 0;
    return true;
}

bool PiFinderBridgeClient::hasOnStepAlignment() const
{
    return m_mountAlignStarsSP != nullptr && m_mountAlignSP != nullptr && m_mountAlignWriteSP != nullptr;
}

bool PiFinderBridgeClient::pressSwitch(INDI::PropertyViewSwitch *property, const char *element)
{
    auto widget = property != nullptr ? property->findWidgetByName(element) : nullptr;
    if (widget == nullptr)
        return false;
    property->reset();
    widget->setState(ISS_ON);
    sendNewSwitch(property);
    return true;
}

bool PiFinderBridgeClient::startOnStepAlignment(int stars)
{
    if (!hasOnStepAlignment() || !pressSwitch(m_mountAlignStarsSP, std::to_string(stars).c_str()))
        return false;
    m_lastMountCommandTime = static_cast<long>(time(nullptr)); // the position changes now, and it is our doing
    return pressSwitch(m_mountAlignSP, "0");                   // "Start Align"
}

bool PiFinderBridgeClient::saveOnStepAlignment()
{
    return pressSwitch(m_mountAlignWriteSP, "0");
}

bool PiFinderBridgeClient::getOnStepAddress(std::string &host, int &driverPort) const
{
    if (m_mountAddressTP == nullptr || m_mountDriverInfoTP == nullptr || m_mountConnectionModeSP == nullptr)
        return false;
    auto exec = m_mountDriverInfoTP->findWidgetByName("DRIVER_EXEC");
    auto tcp = m_mountConnectionModeSP->findWidgetByName("CONNECTION_TCP");
    auto address = m_mountAddressTP->findWidgetByName("ADDRESS");
    auto port = m_mountAddressTP->findWidgetByName("PORT");
    if (exec == nullptr || std::string(exec->getText()).find("lx200_OnStep") == std::string::npos || tcp == nullptr ||
        tcp->getState() != ISS_ON || address == nullptr || port == nullptr || address->getText()[0] == '\0')
        return false;
    host = address->getText();
    driverPort = atoi(port->getText());
    return true;
}

bool PiFinderBridgeClient::justBound() const
{
    return static_cast<long>(time(nullptr)) - m_bindTime < TARGET_EVENT_IGNORE_AFTER_BIND_SEC;
}

void PiFinderBridgeClient::noteMountEvent(MountEvent event, double ra, double dec)
{
    std::lock_guard<std::mutex> lock(m_mountEventMutex);
    m_mountEvent = event;
    m_mountEventRA = ra;
    m_mountEventDec = dec;
}

void PiFinderBridgeClient::noteMountTarget(INDI::Property property)
{
    auto target = property.getNumber();
    const double ra = target->at(0)->getValue(), dec = target->at(1)->getValue();
    if (justBound())
        return noteIgnoredTarget("it arrived right after the Bridge (re)connected", ra, dec);
    if (property.getState() == IPS_ALERT)
        return noteIgnoredTarget("the mount driver marks it as failed", ra, dec);
    if (!std::isfinite(ra) || !std::isfinite(dec) || ra < 0.0 || ra > 24.0 || dec < -90.0 || dec > 90.0 ||
        (ra == 0.0 && dec == 0.0))
        return;
    {
        std::lock_guard<std::mutex> lock(m_mountEventMutex);
        rememberIndiGoto(ra, dec);
        const long now = static_cast<long>(time(nullptr));
        while (!m_ownGotos.empty() && now - m_ownGotos.front().time > OWN_GOTO_ECHO_SEC)
            m_ownGotos.pop_front();
        for (auto it = m_ownGotos.begin(); it != m_ownGotos.end(); ++it)
        {
            if (separationArcmin(ra, dec, it->ra, it->dec) < OWN_GOTO_ECHO_ARCMIN)
            {
                m_ownGotos.erase(it);
                return;
            }
        }
    }
    double mountRA, mountDec;
    if (getMountRADE(mountRA, mountDec) && separationArcmin(ra, dec, mountRA, mountDec) < TARGET_AT_MOUNT_ARCMIN)
        return noteIgnoredTarget("the mount already reports that position (a direction button was released)", ra, dec);
    noteMountEvent(MountEvent::GOTO, ra, dec);
}

void PiFinderBridgeClient::noteIgnoredTarget(const char *why, double ra, double dec)
{
    char text[200];
    snprintf(text, sizeof(text), "New mount target RA %.4fh, DEC %.4f deg not taken as a GoTo: %s.", ra, dec, why);
    std::lock_guard<std::mutex> lock(m_mountEventMutex);
    m_ignoredTargetNote = text;
}

std::string PiFinderBridgeClient::consumeIgnoredTargetNote()
{
    std::lock_guard<std::mutex> lock(m_mountEventMutex);
    std::string note;
    note.swap(m_ignoredTargetNote);
    return note;
}

PiFinderBridgeClient::MountEvent PiFinderBridgeClient::consumeMountEvent(double &ra, double &dec)
{
    std::lock_guard<std::mutex> lock(m_mountEventMutex);
    const MountEvent event = m_mountEvent;
    ra = m_mountEventRA;
    dec = m_mountEventDec;
    m_mountEvent = MountEvent::NONE;
    return event;
}

double PiFinderBridgeClient::secondsSinceForeignMountSync() const
{
    if (m_lastForeignSyncTime == 0)
        return 1e9;
    return static_cast<double>(static_cast<long>(time(nullptr)) - m_lastForeignSyncTime);
}

void PiFinderBridgeClient::updateProperty(INDI::Property property)
{
    const bool fromMount = m_mountName == property.getDeviceName();
    const bool fromPiFinder = m_piFinderName == property.getDeviceName();

    if (fromMount && property.isNameMatch("EQUATORIAL_EOD_COORD"))
        noteMountMotionState(property);

    if (fromMount && property.isNameMatch("EQUATORIAL_EOD_COORD") && property.getState() == IPS_ALERT)
    {
        std::lock_guard<std::mutex> lock(m_mountRejectMutex);
        m_mountRejectedLastCoords = true;
    }
    else if (fromMount && (property.isNameMatch("TELESCOPE_PARK") || property.isNameMatch("TELESCOPE_HOME") ||
                           property.isNameMatch("OnStep Status")))
    {
        noteMountRest(property);
    }
    else if (fromMount && property.isNameMatch("TARGET_EOD_COORD"))
    {
        noteIndiMovement();
        m_lastMountTargetTime = static_cast<long>(time(nullptr));
        releaseKeptTarget(true, property.getNumber()->at(0)->getValue(), property.getNumber()->at(1)->getValue());
        noteMountTarget(property);
    }
    else if (fromMount && property.isNameMatch("Align Process"))
    {
        noteOnStepAlignStatus(property);
    }
    else if (fromMount && property.isNameMatch("TELESCOPE_ABORT_MOTION"))
    {
        noteIndiMovement();
        if (!justBound())
            noteMountEvent(MountEvent::ABORT);
    }
    else if (fromMount && (property.isNameMatch("TELESCOPE_MOTION_NS") || property.isNameMatch("TELESCOPE_MOTION_WE")))
    {
        noteIndiMovement();
        if (!justBound() && property.getSwitch()->findOnSwitchIndex() >= 0)
            noteMountEvent(MountEvent::HAND_MOTION);
    }
    else if (fromMount && property.isNameMatch("ON_COORD_SET"))
    {
        auto sync = property.getSwitch()->findWidgetByName("SYNC");
        if (!justBound() && sync != nullptr && sync->getState() == ISS_ON &&
            secondsSinceLastMountCommand() > OWN_COMMAND_SWITCH_SEC)
        {
            m_lastForeignSyncTime = static_cast<long>(time(nullptr));
            ++m_foreignSyncCount;
        }
    }
    else if (fromPiFinder && property.isNameMatch("TARGET_EOD_COORD"))
    {
        m_lastPiFinderTargetTime = static_cast<long>(time(nullptr));
        // Every genuine Goto request on the PiFinder device re-publishes
        // this property (see consumePiFinderTargetPending()'s own comment
        // in the header) - mark it pending regardless of whether the value
        // actually changed from last time.
        if (static_cast<long>(time(nullptr)) - m_bindTime >= TARGET_EVENT_IGNORE_AFTER_BIND_SEC)
        {
            releaseKeptTarget(false, 0.0, 0.0);
            std::lock_guard<std::mutex> lock(m_piFinderTargetMutex);
            m_piFinderTargetPending = true;
        }
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
    if (m_mountName == property.getDeviceName() && property.isNameMatch("Align Process"))
    {
        std::lock_guard<std::mutex> lock(m_alignStatusMutex);
        m_alignStatusKnown = false; // the mount driver disconnected: no statement about its controller any more
        return;
    }
    if (property.getNumber() == m_piFinderEqNP)
        m_piFinderEqNP = nullptr;
    else if (property.getNumber() == m_piFinderTargetNP)
        m_piFinderTargetNP = nullptr;
    else if (property.getNumber() == m_mountEqNP)
        m_mountEqNP = nullptr;
    else if (property.getNumber() == m_piFinderGeoNP)
        m_piFinderGeoNP = nullptr;
    else if (property.getNumber() == m_mountGeoNP)
        m_mountGeoNP = nullptr;
    else if (property.getNumber() == m_mountTargetNP)
        m_mountTargetNP = nullptr;
    else if (property.getText() == m_mountAddressTP)
        m_mountAddressTP = nullptr;
    else if (property.getText() == m_mountDriverInfoTP)
        m_mountDriverInfoTP = nullptr;
    else if (property.getSwitch() == m_mountConnectionModeSP)
        m_mountConnectionModeSP = nullptr;
    else if (property.getSwitch() == m_mountAlignStarsSP)
        m_mountAlignStarsSP = nullptr;
    else if (property.getSwitch() == m_mountAlignSP)
        m_mountAlignSP = nullptr;
    else if (property.getSwitch() == m_mountAlignWriteSP)
        m_mountAlignWriteSP = nullptr;
    else if (property.getSwitch() == m_mountOnCoordSetSP)
        m_mountOnCoordSetSP = nullptr;
    else if (property.getSwitch() == m_mountParkSP)
        m_mountParkSP = nullptr;
    else if (property.getSwitch() == m_piFinderOnCoordSetSP)
        m_piFinderOnCoordSetSP = nullptr;
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

bool PiFinderBridgeClient::getObserverLocation(double &lat, double &lon, std::string &source) const
{
    auto read = [](INDI::PropertyViewNumber *np, double &la, double &lo) -> bool
    {
        if (np == nullptr)
            return false;
        auto latW = np->findWidgetByName("LAT");
        auto lonW = np->findWidgetByName("LONG");
        if (latW == nullptr || lonW == nullptr)
            return false;
        la = latW->getValue();
        lo = lonW->getValue();
        if (!std::isfinite(la) || !std::isfinite(lo) || std::fabs(la) > 90.0 || std::fabs(lo) > 360.0)
            return false;
        if (std::fabs(la) < 1e-9 && std::fabs(lo) < 1e-9)
            return false; // INDI's default for "never set" - not a real location
        if (lo > 180.0)
            lo -= 360.0;
        return true;
    };

    if (read(m_piFinderGeoNP, lat, lon))
    {
        source = "INDI location of the PiFinder device (KStars / StellarMate app)";
        return true;
    }
    if (read(m_mountGeoNP, lat, lon))
    {
        source = "INDI location of the mount (KStars / StellarMate app)";
        return true;
    }
    return false;
}

void PiFinderBridgeClient::beginOwnRun()
{
    KeptTarget before;
    before.have = getLastGotoTarget(before.ra, before.dec, &before.source, &before.time);
    before.active = true;
    std::lock_guard<std::mutex> lock(m_mountEventMutex);
    m_keptTarget = before; // a second run right after the first keeps the same one: getLastGotoTarget() still answers it
    m_ownRun = true;
    m_ownRunCoords.clear();
}

void PiFinderBridgeClient::endOwnRun()
{
    std::lock_guard<std::mutex> lock(m_mountEventMutex);
    m_ownRun = false;
}

void PiFinderBridgeClient::releaseKeptTarget(bool fromMount, double ra, double dec)
{
    std::lock_guard<std::mutex> lock(m_mountEventMutex);
    if (!m_keptTarget.active)
        return;
    if (fromMount)
    {
        if (m_ownRun)
            return;
        for (const auto &own : m_ownRunCoords)
        {
            if (separationArcmin(ra, dec, own.first, own.second) < OWN_GOTO_ECHO_ARCMIN)
                return;
        }
    }
    m_keptTarget.active = false;
}

bool PiFinderBridgeClient::getLastGotoTarget(double &ra, double &dec, TargetOrigin *source, long *setTime) const
{
    {
        std::lock_guard<std::mutex> lock(m_mountEventMutex);
        if (m_keptTarget.active)
        {
            if (!m_keptTarget.have)
                return false;
            ra = m_keptTarget.ra;
            dec = m_keptTarget.dec;
            if (source != nullptr)
                *source = m_keptTarget.source;
            if (setTime != nullptr)
                *setTime = m_keptTarget.time;
            return true;
        }
    }
    return getReportedGotoTarget(ra, dec, source, setTime);
}

bool PiFinderBridgeClient::getReportedGotoTarget(double &ra, double &dec, TargetOrigin *source, long *setTime) const
{
    auto valid = [](double r, double d) { return std::isfinite(r) && std::isfinite(d) && d >= -90.0 && d <= 90.0 && !(r == 0.0 && d == 0.0); };
    bool found = false;
    long newest = 0;
    // Later calls win a tie: PiFinder over the mount only when strictly newer, the controller over both.
    auto take = [&](bool have, double r, double d, long when, TargetOrigin origin, bool winsTie)
    {
        if (!have || !valid(r, d) || (found && (when < newest || (when == newest && !winsTie))))
            return;
        found = true;
        newest = when;
        ra = r;
        dec = d;
        if (source != nullptr)
            *source = origin;
        if (setTime != nullptr)
            *setTime = when;
    };
    const bool haveMount = m_mountTargetNP != nullptr;
    const double mountRA = haveMount ? m_mountTargetNP->at(0)->getValue() : 0.0;
    const double mountDec = haveMount ? m_mountTargetNP->at(1)->getValue() : 0.0;
    bool haveController;
    double controllerRA, controllerDec;
    long controllerTime;
    {
        std::lock_guard<std::mutex> lock(m_mountEventMutex);
        haveController = m_haveControllerTarget;
        controllerRA = m_controllerTargetRA;
        controllerDec = m_controllerTargetDec;
        controllerTime = m_controllerTargetTime;
    }
    take(haveMount, mountRA, mountDec, m_lastMountTargetTime, TargetOrigin::MOUNT, false);
    take(haveController, controllerRA, controllerDec, controllerTime, TargetOrigin::CONTROLLER, true);
    if (m_piFinderTargetNP != nullptr)
    {
        // The same coordinates on the PiFinder device are the Bridge telling PiFinder about a GoTo made elsewhere.
        const double piRA = m_piFinderTargetNP->at(0)->getValue(), piDec = m_piFinderTargetNP->at(1)->getValue();
        const bool echo = found && valid(piRA, piDec) && separationArcmin(piRA, piDec, ra, dec) < OWN_GOTO_ECHO_ARCMIN;
        take(!echo, piRA, piDec, m_lastPiFinderTargetTime, TargetOrigin::PIFINDER, false);
    }
    return found;
}

bool PiFinderBridgeClient::getPiFinderTargetRADE(double &ra, double &dec) const
{
    if (m_piFinderTargetNP == nullptr)
        return false;

    ra = m_piFinderTargetNP->at(0)->getValue();
    dec = m_piFinderTargetNP->at(1)->getValue();
    return isUsableCoordinateForWarn("PiFinder target", ra, dec);
}

bool PiFinderBridgeClient::hasPiFinderTargetPending() const
{
    std::lock_guard<std::mutex> lock(m_piFinderTargetMutex);
    return m_piFinderTargetPending;
}

std::string PiFinderBridgeClient::missingDevices() const
{
    std::string missing;
    if (m_piFinderEqNP == nullptr)
        missing = m_piFinderName;
    if (m_mountEqNP == nullptr || m_mountOnCoordSetSP == nullptr)
        missing += (missing.empty() ? "" : ", ") + m_mountName;
    return missing;
}

bool PiFinderBridgeClient::consumePiFinderTargetPending()
{
    std::lock_guard<std::mutex> lock(m_piFinderTargetMutex);
    const bool wasPending = m_piFinderTargetPending;
    m_piFinderTargetPending = false;
    return wasPending;
}

bool PiFinderBridgeClient::getMountParked(bool &parked) const
{
    if (m_mountParkSP == nullptr)
        return false;
    auto park = m_mountParkSP->findWidgetByName("PARK");
    if (park == nullptr)
        return false;
    parked = park->getState() == ISS_ON;
    return true;
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

// The last line of defence before anything reaches a mount: a coordinate that cannot exist is never sent (seen live: Dec 113.5, RA 31.5 h).
static bool plausibleEquatorial(double ra, double dec)
{
    return std::isfinite(ra) && std::isfinite(dec) && ra >= 0.0 && ra <= 24.0 && dec >= -90.0 && dec <= 90.0;
}

bool PiFinderBridgeClient::sendMountCoords(double ra, double dec, const char *coordSetName)
{
    if (!isReady())
        return false;

    if (!plausibleEquatorial(ra, dec))
        return false;

    auto coordSetSwitch = m_mountOnCoordSetSP->findWidgetByName(coordSetName);
    if (coordSetSwitch == nullptr)
        return false;

    {
        std::lock_guard<std::mutex> lock(m_mountRejectMutex);
        m_mountRejectedLastCoords = false;
        m_mountRejectMessage.clear();
    }

    // Both noted before anything is sent: the answers arrive on the client's own thread.
    m_lastMountCommandTime = static_cast<long>(time(nullptr));
    {
        std::lock_guard<std::mutex> lock(m_mountEventMutex);
        if (m_ownRun)
            m_ownRunCoords.emplace_back(ra, dec);
    }
    if (std::string(coordSetName) != "SYNC")
    {
        std::lock_guard<std::mutex> lock(m_mountEventMutex);
        m_ownGotos.push_back({ ra, dec, static_cast<long>(time(nullptr)) });
        rememberIndiGoto(ra, dec);
    }

    m_mountOnCoordSetSP->reset();
    coordSetSwitch->setState(ISS_ON);
    sendNewSwitch(m_mountOnCoordSetSP);

    m_mountEqNP->at(0)->setValue(ra);
    m_mountEqNP->at(1)->setValue(dec);
    m_mountEqNP->setState(IPS_BUSY);
    sendNewNumber(m_mountEqNP);

    return true;
}

bool PiFinderBridgeClient::sendPiFinderCoords(double ra, double dec, const char *coordSetName)
{
    if (!isReady() || m_piFinderOnCoordSetSP == nullptr)
        return false;

    auto coordSetSwitch = m_piFinderOnCoordSetSP->findWidgetByName(coordSetName);
    if (coordSetSwitch == nullptr)
        return false;

    m_piFinderOnCoordSetSP->reset();
    coordSetSwitch->setState(ISS_ON);
    sendNewSwitch(m_piFinderOnCoordSetSP);

    m_piFinderEqNP->at(0)->setValue(ra);
    m_piFinderEqNP->at(1)->setValue(dec);
    sendNewNumber(m_piFinderEqNP);

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
