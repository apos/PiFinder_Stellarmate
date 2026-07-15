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

#include <memory>

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

        std::unique_ptr<PiFinderBridgeClient> m_client;

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
        ISwitch BridgeModeS[3];
        enum { MODE_OFF, MODE_VERIFY_ALERT, MODE_AUTO_CORRECT };

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
};
