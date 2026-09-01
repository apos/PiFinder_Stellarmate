#include "pifinder_simulator.h"

#include <cstring>

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
        defineProperty(PushToTargetNP);
    else
        deleteProperty(PushToTargetNP);

    return true;
}

bool PiFinderSimulator::Connect()
{
    LOG_INFO("PiFinder Simulator connected.");
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
