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

        // Settings: how to reach the local indiserver
        ITextVectorProperty SettingsTP;
        IText SettingsT[2] {};
        enum { INDISERVER_HOST, INDISERVER_PORT };

        // Which devices to bridge
        ITextVectorProperty ActiveDeviceTP;
        IText ActiveDeviceT[2] {};
        enum { ACTIVE_PIFINDER, ACTIVE_MOUNT };

        // Coupling degree - see 00009 for the rationale of each stage
        ISwitchVectorProperty BridgeModeSP;
        ISwitch BridgeModeS[4];
        enum { MODE_OFF, MODE_VERIFY_ALERT, MODE_AUTO_CORRECT, MODE_GOTO_FORWARD };

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

        void handleGotoForward();
};
