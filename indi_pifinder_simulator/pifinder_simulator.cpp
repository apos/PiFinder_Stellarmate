#include "pifinder_simulator.h"

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
