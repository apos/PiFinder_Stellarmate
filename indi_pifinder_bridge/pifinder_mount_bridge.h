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

        // Last-applied ACTIVE_DEVICES values, used by ISNewText() to detect
        // a genuine change worth reconnecting for. Deliberately NOT read
        // from ActiveDeviceT[...].text before IUUpdateText() runs - that
        // crashed (2026-08-05) when ISNewText() fires from loadConfig()'s
        // config replay inside ISGetProperties(). Populated from the
        // same defaults as ActiveDeviceT in initProperties(), then kept in
        // sync after every applied update.
        std::string m_lastActivePiFinder;
        std::string m_lastActiveMount;

        // Settings: how to reach the local indiserver
        ITextVectorProperty SettingsTP;
        IText SettingsT[2] {};
        enum { INDISERVER_HOST, INDISERVER_PORT };

        // Which devices to bridge
        ITextVectorProperty ActiveDeviceTP;
        IText ActiveDeviceT[2] {};
        enum { ACTIVE_PIFINDER, ACTIVE_MOUNT };

        // Coupling degree - see 00009 for the rationale of each stage.
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

        // Emergency stop - sends TELESCOPE_ABORT_MOTION to the active mount
        // immediately, independent of Coupling mode or any in-progress
        // settle-retry cycle. Separate property from ManualTriggerSP
        // (rather than a third option there) so it's never gated behind
        // the same handler path as Sync/Goto - a panic button should stay
        // as simple and direct as possible. See #179 (found live
        // 2026-08-07: Mount Bridge had no way at all to stop the mount if
        // a settle-retry cycle went wrong, e.g. #177's missing
        // dead-reckoning made it sync onto a stale position and re-slew
        // repeatedly).
        ISwitchVectorProperty AbortMountSP;
        ISwitch AbortMountS[1];

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
        static constexpr int SETTLE_TICKS = 3; // poll cycles to wait before even checking for a fresh solve

        // SETTLE_TICKS alone doesn't guarantee PiFinder has actually produced
        // a new camera solve by then - it may still be reporting an
        // IMU-interpolated position left over from before/during the slew.
        // Trusting that as arrival truth would Sync the mount to a guessed
        // position instead of a verified one, corrupting its model instead
        // of correcting it. Found live (2026-08-07): this caused PiFinder's
        // own reported position to overshoot the target and the mount to
        // never converge across retries - same failure class #79 already
        // guards against for Auto-Correct, just missing here. Bounded so a
        // stuck/slow solver can't stall a settle attempt forever.
        int m_freshnessWaitTicksRemaining = 0;
        static constexpr int MAX_FRESHNESS_WAIT_TICKS = 10;

        // A residual after arrival usually means the mount's own model was
        // slightly off at this sky position - Sync corrects that model with
        // PiFinder's solve, then re-issuing the Goto (now benefiting from
        // the corrected model) should land closer. Bounded so a genuinely
        // noisy solve can't loop forever chasing it.
        int m_settleRetriesRemaining = 0;
        static constexpr int MAX_SETTLE_RETRIES = 3;

        void handleGotoForward();

        // MODE_AUTO_CORRECT with CorrectionActionS[ACTION_GOTO]: mirrors
        // handleGotoForward()'s arrival-verify-and-refine pattern (#170 -
        // blindly re-issuing a Goto to wherever PiFinder currently reports,
        // every single tick drift exceeds threshold, never corrects the
        // mount's own alignment-model error, so each Goto lands off by
        // roughly that same fixed error and drift climbs straight back up
        // right after - never actually converges on the target). Kept as a
        // separate state machine rather than reusing ForwardState/
        // handleGotoForward(): that one is driven by a discrete *new*
        // PiFinder push-to target event; this one is driven by continuous
        // drift-exceeds-threshold and needs to hand control back to normal
        // per-tick monitoring once a correction settles, not wait for a
        // "new target" event that may never come.
        enum class CorrectState { IDLE, SLEWING, SETTLING };
        CorrectState m_correctState = CorrectState::IDLE;
        double m_correctTargetRA = std::nan("");
        double m_correctTargetDec = std::nan("");
        int m_correctSettleTicksRemaining = 0;
        int m_correctFreshnessWaitTicksRemaining = 0;
        int m_correctSettleRetriesRemaining = 0;

        void handleAutoCorrectGoto(bool exceeded, double piRA, double piDec, double drift, double threshold);
};
