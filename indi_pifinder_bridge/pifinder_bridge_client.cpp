#include "pifinder_bridge_client.h"

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

    watchDevice(m_piFinderName.c_str());
    watchDevice(m_mountName.c_str());
}

bool PiFinderBridgeClient::isReady() const
{
    return m_piFinderEqNP != nullptr && m_mountEqNP != nullptr && m_mountOnCoordSetSP != nullptr;
}

void PiFinderBridgeClient::newDevice(INDI::BaseDevice dp)
{
    if (dp.isDeviceNameMatch(m_piFinderName))
        m_piFinderOnline = true;
    if (dp.isDeviceNameMatch(m_mountName))
        m_mountOnline = true;
}

void PiFinderBridgeClient::newProperty(INDI::Property property)
{
    const bool fromPiFinder = m_piFinderName == property.getDeviceName();
    const bool fromMount = m_mountName == property.getDeviceName();

    if (fromMount && property.isNameMatch("EQUATORIAL_EOD_COORD"))
        m_mountEqNP = property.getNumber();
    else if (fromMount && property.isNameMatch("ON_COORD_SET"))
        m_mountOnCoordSetSP = property.getSwitch();
    else if (fromPiFinder && property.isNameMatch("EQUATORIAL_EOD_COORD"))
        m_piFinderEqNP = property.getNumber();
    else if (fromPiFinder && property.isNameMatch("TARGET_EOD_COORD"))
        m_piFinderTargetNP = property.getNumber();
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
}

bool PiFinderBridgeClient::getPiFinderRADE(double &ra, double &dec) const
{
    if (m_piFinderEqNP == nullptr)
        return false;

    ra = m_piFinderEqNP->at(0)->getValue();
    dec = m_piFinderEqNP->at(1)->getValue();
    return true;
}

bool PiFinderBridgeClient::getMountRADE(double &ra, double &dec) const
{
    if (m_mountEqNP == nullptr)
        return false;

    ra = m_mountEqNP->at(0)->getValue();
    dec = m_mountEqNP->at(1)->getValue();
    return true;
}

bool PiFinderBridgeClient::getPiFinderTargetRADE(double &ra, double &dec) const
{
    if (m_piFinderTargetNP == nullptr)
        return false;

    ra = m_piFinderTargetNP->at(0)->getValue();
    dec = m_piFinderTargetNP->at(1)->getValue();
    return true;
}

bool PiFinderBridgeClient::isMountSlewing() const
{
    return m_mountEqNP != nullptr && m_mountEqNP->getState() == IPS_BUSY;
}

bool PiFinderBridgeClient::sendMountCoords(double ra, double dec, const char *coordSetName)
{
    if (!isReady())
        return false;

    auto coordSetSwitch = m_mountOnCoordSetSP->findWidgetByName(coordSetName);
    if (coordSetSwitch == nullptr)
        return false;

    m_mountOnCoordSetSP->reset();
    coordSetSwitch->setState(ISS_ON);
    sendNewSwitch(m_mountOnCoordSetSP);

    m_mountEqNP->at(0)->setValue(ra);
    m_mountEqNP->at(1)->setValue(dec);
    m_mountEqNP->setState(IPS_BUSY);
    sendNewNumber(m_mountEqNP);

    return true;
}
