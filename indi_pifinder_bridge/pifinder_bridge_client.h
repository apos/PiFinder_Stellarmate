/*
    PiFinder Mount Bridge - internal INDI client

    Connects to the local indiserver as a plain client (same pattern as the
    stock indi_skysafari driver's SkySafariClient) and watches two devices:
    the PiFinder position source and whichever real mount device is active.
    Never speaks any mount-specific protocol - only the generic
    EQUATORIAL_EOD_COORD / ON_COORD_SET properties every INDI telescope
    driver already exposes.
*/

#pragma once

#include "baseclient.h"
#include "basedevice.h"

#include <string>

class PiFinderBridgeClient : public INDI::BaseClient
{
    public:
        PiFinderBridgeClient();

        void setDevices(const std::string &piFinderName, const std::string &mountName);

        bool isReady() const;

        bool getPiFinderRADE(double &ra, double &dec) const;
        bool getMountRADE(double &ra, double &dec) const;

        // The last push-to target requested via a Goto() on the PiFinder
        // device - distinct from getPiFinderRADE(), which is PiFinder's live
        // solved position and never changes just because a target was set.
        bool getPiFinderTargetRADE(double &ra, double &dec) const;

        // True while the mount is actively slewing (EQUATORIAL_EOD_COORD busy).
        bool isMountSlewing() const;

        // coordSetName is one of the mount's ON_COORD_SET switch names, e.g. "SYNC", "TRACK", "SLEW"
        bool sendMountCoords(double ra, double dec, const char *coordSetName);

    protected:
        void newDevice(INDI::BaseDevice dp) override;
        void newProperty(INDI::Property property) override;
        void removeProperty(INDI::Property property) override;

    private:
        std::string m_piFinderName;
        std::string m_mountName;
        bool m_piFinderOnline = false;
        bool m_mountOnline = false;

        INDI::PropertyViewNumber *m_piFinderEqNP = nullptr;
        INDI::PropertyViewNumber *m_piFinderTargetNP = nullptr;
        INDI::PropertyViewNumber *m_mountEqNP = nullptr;
        INDI::PropertyViewSwitch *m_mountOnCoordSetSP = nullptr;
};
