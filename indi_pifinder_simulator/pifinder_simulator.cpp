#include "pifinder_simulator.h"

#include <cstring>

static std::unique_ptr<PiFinderSimulator> pifinder_simulator(new PiFinderSimulator());

PiFinderSimulator::PiFinderSimulator()
{
    setVersion(1, 0);
    SetTelescopeCapability(TELESCOPE_CAN_GOTO | TELESCOPE_CAN_SYNC | TELESCOPE_CAN_ABORT, 1);
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

    return true;
}

bool PiFinderSimulator::updateProperties()
{
    INDI::Telescope::updateProperties();

    if (isConnected())
        defineProperty(PushToTargetNP);
    else
        deleteProperty(PushToTargetNP);

    return true;
}

bool PiFinderSimulator::Connect()
{
    LOG_INFO("PiFinder Simulator connected.");
    return true;
}

bool PiFinderSimulator::Disconnect()
{
    LOG_INFO("PiFinder Simulator disconnected.");
    return true;
}

bool PiFinderSimulator::ReadScopeStatus()
{
    // Deliberately never changes on its own between Sync()/Goto() calls -
    // see the header comment: this device holds still exactly where it was
    // put, so a test session always knows precisely what "sky truth" it's
    // currently feeding PiFinder.
    NewRaDec(m_currentRA, m_currentDEC);
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
    TrackState = SCOPE_TRACKING;
    LOGF_INFO("Goto: RA %.4fh, DEC %.4f deg.", ra, dec);
    NewRaDec(m_currentRA, m_currentDEC);
    return true;
}

bool PiFinderSimulator::Sync(double ra, double dec)
{
    m_currentRA = ra;
    m_currentDEC = dec;
    TrackState = SCOPE_TRACKING;
    LOGF_INFO("Sync: RA %.4fh, DEC %.4f deg.", ra, dec);
    NewRaDec(m_currentRA, m_currentDEC);
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
