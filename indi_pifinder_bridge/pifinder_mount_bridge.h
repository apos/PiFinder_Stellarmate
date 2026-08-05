/*
    PiFinder Mount Bridge

    Generic, mount-agnostic coupling between PiFinder's plate-solved position
    and whichever real INDI mount driver is active. Never speaks a
    mount-specific wire protocol - only the standard EQUATORIAL_EOD_COORD /
    ON_COORD_SET properties every INDI telescope driver already exposes, via
    an internal INDI client (same pattern as the stock indi_skysafari
    driver).

    See basic-memory pifinder-stellarmate/00009_indi-mount-bridge-concept for
    the design rationale (the "coupling degree" dial below).
*/

#pragma once

#include "defaultdevice.h"

#include <cmath>
#include <memory>
#include <string>

class PiFinderBridgeClient;

class PiFinderMountBridge : public INDI::DefaultDevice
{
    public:
        PiFinderMountBridge();

        virtual void ISGetProperties(const char *dev) override;
        virtual bool ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n) override;
        virtual bool ISNewSwitch(const char *dev, const char *name, ISState *states, char *names[], int n) override;
        virtual bool ISNewNumber(const char *dev, const char *name, double values[], char *names[], int n) override;

    protected:
        virtual bool initProperties() override;
        virtual bool updateProperties() override;
        virtual bool Connect() override;
        virtual bool Disconnect() override;
        virtual const char *getDefaultName() override;
        virtual void TimerHit() override;
        virtual bool saveConfigItems(FILE *fp) override;

    private:
        void applyMode();
        double angularSeparationArcmin(double ra1, double dec1, double ra2, double dec2) const;

        // Pushes the active mount's TELESCOPE_MOUNT_TYPE (Alt/Az vs EQ) to
        // PiFinder's own Mount Type setting via HTTP, independent of
        // BridgeModeSP - this should stay in sync regardless of which
        // coupling mode (or Off) is selected. No-op if unchanged since the
        // last successful push, or if the mount hasn't reported it yet.
        void syncMountTypeToPiFinder();
        std::string m_lastSyncedMountType;

        std::unique_ptr<PiFinderBridgeClient> m_client;

        // ISGetProperties() fires once per client connection (every
        // indi_getprop call, every INDI Control Panel refresh) - guard so
        // loadConfig() only actually replays the saved config once, or a
        // later client re-querying properties would silently revert
        // whatever mode the user just chose back to the last-saved one.
        bool m_configLoaded = false;

        // Same idea, for the properties that only exist once connected
        // (BRIDGE_MODE, CORRECTION_ACTION, DRIFT_THRESHOLD,
        // SOLVE_FRESHNESS) - ISGetProperties() runs before the device is
        // connected, so its loadConfig() call above has nothing to apply
        // BRIDGE_MODE's saved value to yet (the property doesn't exist as a
        // target). Found live (2026-08-05): Coupling mode never survived a
        // reconnect/profile restart, always came back up as whatever
        // in-memory default the switch was initialized with, regardless of
        // what was actually saved on disk.
        bool m_connectedConfigLoaded = false;

        // Settings: how to reach the local indiserver
        ITextVectorProperty SettingsTP;
        IText SettingsT[2] {};
        enum { INDISERVER_HOST, INDISERVER_PORT };

        // Which devices to bridge
        ITextVectorProperty ActiveDeviceTP;
        IText ActiveDeviceT[2] {};
        enum { ACTIVE_PIFINDER, ACTIVE_MOUNT };

        // Coupling degree - see 00009 for the rationale of each stage.
        // MODE_MOUNT_SOURCE (see #130) reverses the usual direction: instead
        // of PiFinder's solve driving the mount, the mount's own position
        // (real or the stock INDI Telescope Simulator) is injected into
        // PiFinder as a Fake-Solve - for testing/demoing without any real
        // PiFinder hardware at all. One-time seeds only (see
        // pushMountPositionToPiFinder()), not literally every tick.
        ISwitchVectorProperty BridgeModeSP;
        ISwitch BridgeModeS[5];
        enum { MODE_OFF, MODE_VERIFY_ALERT, MODE_AUTO_CORRECT, MODE_GOTO_FORWARD, MODE_MOUNT_SOURCE };

        // AUTO_CORRECT sends Sync or Goto/Track - separate from the above so
        // the one-shot manual actions below can also pick either.
        ISwitchVectorProperty CorrectionActionSP;
        ISwitch CorrectionActionS[2];
        enum { ACTION_SYNC, ACTION_GOTO };

        // Manual, immediate one-shot trigger (works regardless of BridgeModeSP)
        ISwitchVectorProperty ManualTriggerSP;
        ISwitch ManualTriggerS[2];
        enum { TRIGGER_SYNC_NOW, TRIGGER_GOTO_NOW };

        INumberVectorProperty DriftThresholdNP;
        INumber DriftThresholdN[1];

        // Auto-correct only fires off a position PiFinder itself reports as
        // a real, recent camera solve (via /api/status - see #79/#107 in
        // basic-memory pifinder-stellarmate: LX200 has no room to carry this,
        // so it's fetched separately over HTTP). This is the max age of that
        // solve for a correction to still be considered trustworthy.
        INumberVectorProperty SolveFreshnessMaxAgeNP;
        INumber SolveFreshnessMaxAgeN[1];

        // Read-only: last computed drift between PiFinder and the mount, for
        // the VERIFY_ALERT mode and general visibility.
        INumberVectorProperty DriftStatusNP;
        INumber DriftStatusN[1];

        // MODE_GOTO_FORWARD state machine: forwards a *new* push-to target
        // to the mount immediately (event-driven, unlike the drift-polling
        // modes above), then waits for the mount to finish slewing and for
        // PiFinder to produce a fresh plate-solve of the arrival position
        // before auto-correcting any residual error. See 00009/00012 in
        // basic-memory pifinder-stellarmate for the design rationale.
        enum class ForwardState { IDLE, SLEWING, SETTLING };
        ForwardState m_forwardState = ForwardState::IDLE;
        double m_lastForwardedRA = std::nan("");
        double m_lastForwardedDec = std::nan("");
        int m_settleTicksRemaining = 0;
        static constexpr int SETTLE_TICKS = 3; // poll cycles to wait for a fresh PiFinder solve after slew

        // A residual after arrival usually means the mount's own model was
        // slightly off at this sky position - Sync corrects that model with
        // PiFinder's solve, then re-issuing the Goto (now benefiting from
        // the corrected model) should land closer. Bounded so a genuinely
        // noisy solve can't loop forever chasing it.
        int m_settleRetriesRemaining = 0;
        static constexpr int MAX_SETTLE_RETRIES = 3;

        void handleGotoForward();

        // MODE_MOUNT_SOURCE: pushes the mount's current position to PiFinder
        // as a Fake-Solve whenever it has moved meaningfully since the last
        // push (not on every tick - that would just be needlessly noisy
        // re-injection of an unchanged position). See #130.
        void handleMountSource();
        double m_lastPushedMountRA = std::nan("");
        double m_lastPushedMountDec = std::nan("");

        // Below this, a mount position change is considered noise/tracking
        // jitter, not a deliberate slew worth re-seeding PiFinder over.
        static constexpr double MOUNT_SOURCE_MIN_CHANGE_ARCMIN = 2.0;
};
