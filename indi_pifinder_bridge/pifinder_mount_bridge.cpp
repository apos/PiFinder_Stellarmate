#include "pifinder_mount_bridge.h"
#include "pifinder_bridge_client.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <memory>

static std::unique_ptr<PiFinderMountBridge> pifinder_bridge(new PiFinderMountBridge());

PiFinderMountBridge::PiFinderMountBridge()
{
    setVersion(1, 0);
    setDriverInterface(AUX_INTERFACE);

    m_client.reset(new PiFinderBridgeClient());
}

const char *PiFinderMountBridge::getDefaultName()
{
    return "PiFinder Mount Bridge";
}

bool PiFinderMountBridge::initProperties()
{
    INDI::DefaultDevice::initProperties();

    IUFillText(&SettingsT[INDISERVER_HOST], "INDISERVER_HOST", "indiserver host", "localhost");
    IUFillText(&SettingsT[INDISERVER_PORT], "INDISERVER_PORT", "indiserver port", "7624");
    IUFillTextVector(&SettingsTP, SettingsT, 2, getDeviceName(), "BRIDGE_SETTINGS", "Settings",
                     "Options", IP_RW, 60, IPS_IDLE);

    IUFillText(&ActiveDeviceT[ACTIVE_PIFINDER], "ACTIVE_PIFINDER", "PiFinder", "PiFinder LX200");
    IUFillText(&ActiveDeviceT[ACTIVE_MOUNT], "ACTIVE_MOUNT", "Mount", "");
    IUFillTextVector(&ActiveDeviceTP, ActiveDeviceT, 2, getDeviceName(), "ACTIVE_DEVICES", "Active devices",
                     "Options", IP_RW, 60, IPS_IDLE);

    IUFillSwitch(&BridgeModeS[MODE_OFF], "MODE_OFF", "Off", ISS_ON);
    IUFillSwitch(&BridgeModeS[MODE_VERIFY_ALERT], "MODE_VERIFY_ALERT", "Verify/Alert only", ISS_OFF);
    IUFillSwitch(&BridgeModeS[MODE_AUTO_CORRECT], "MODE_AUTO_CORRECT", "Auto-correct on drift", ISS_OFF);
    IUFillSwitchVector(&BridgeModeSP, BridgeModeS, 3, getDeviceName(), "BRIDGE_MODE", "Coupling",
                       "Main Control", IP_RW, ISR_1OFMANY, 60, IPS_IDLE);

    IUFillSwitch(&CorrectionActionS[ACTION_SYNC], "ACTION_SYNC", "Sync", ISS_ON);
    IUFillSwitch(&CorrectionActionS[ACTION_GOTO], "ACTION_GOTO", "Goto/Track", ISS_OFF);
    IUFillSwitchVector(&CorrectionActionSP, CorrectionActionS, 2, getDeviceName(), "CORRECTION_ACTION",
                       "Auto-correct action", "Main Control", IP_RW, ISR_1OFMANY, 60, IPS_IDLE);

    IUFillSwitch(&ManualTriggerS[TRIGGER_SYNC_NOW], "TRIGGER_SYNC_NOW", "Sync Now", ISS_OFF);
    IUFillSwitch(&ManualTriggerS[TRIGGER_GOTO_NOW], "TRIGGER_GOTO_NOW", "Goto Now", ISS_OFF);
    IUFillSwitchVector(&ManualTriggerSP, ManualTriggerS, 2, getDeviceName(), "MANUAL_TRIGGER",
                       "Manual (one-shot)", "Main Control", IP_RW, ISR_ATMOST1, 60, IPS_IDLE);

    IUFillNumber(&DriftThresholdN[0], "THRESHOLD_ARCMIN", "Threshold (arcmin)", "%.1f", 0.1, 600, 0.5, 5);
    IUFillNumberVector(&DriftThresholdNP, DriftThresholdN, 1, getDeviceName(), "DRIFT_THRESHOLD",
                       "Drift Threshold", "Main Control", IP_RW, 60, IPS_IDLE);

    IUFillNumber(&DriftStatusN[0], "DRIFT_ARCMIN", "Current drift (arcmin)", "%.2f", 0, 10000, 0, 0);
    IUFillNumberVector(&DriftStatusNP, DriftStatusN, 1, getDeviceName(), "DRIFT_STATUS", "Status",
                       "Main Control", IP_RO, 60, IPS_IDLE);

    addDebugControl();
    setDefaultPollingPeriod(2000);

    return true;
}

void PiFinderMountBridge::ISGetProperties(const char *dev)
{
    DefaultDevice::ISGetProperties(dev);

    defineProperty(&SettingsTP);
    defineProperty(&ActiveDeviceTP);

    loadConfig(true);
}

bool PiFinderMountBridge::updateProperties()
{
    DefaultDevice::updateProperties();

    if (isConnected())
    {
        defineProperty(&BridgeModeSP);
        defineProperty(&CorrectionActionSP);
        defineProperty(&ManualTriggerSP);
        defineProperty(&DriftThresholdNP);
        defineProperty(&DriftStatusNP);
    }
    else
    {
        deleteProperty(BridgeModeSP.name);
        deleteProperty(CorrectionActionSP.name);
        deleteProperty(ManualTriggerSP.name);
        deleteProperty(DriftThresholdNP.name);
        deleteProperty(DriftStatusNP.name);
    }

    return true;
}

bool PiFinderMountBridge::Connect()
{
    const std::string piFinderName = ActiveDeviceT[ACTIVE_PIFINDER].text;
    const std::string mountName = ActiveDeviceT[ACTIVE_MOUNT].text;

    if (mountName.empty())
    {
        LOG_ERROR("No mount device configured - set Active devices -> Mount first.");
        return false;
    }

    m_client->setServer(SettingsT[INDISERVER_HOST].text, std::stoi(SettingsT[INDISERVER_PORT].text));
    m_client->setDevices(piFinderName, mountName);

    if (!m_client->connectServer())
    {
        LOGF_ERROR("Failed to connect to indiserver at %s:%s", SettingsT[INDISERVER_HOST].text,
                   SettingsT[INDISERVER_PORT].text);
        return false;
    }

    LOGF_INFO("Bridging %s -> %s.", piFinderName.c_str(), mountName.c_str());
    SetTimer(getCurrentPollingPeriod());
    return true;
}

bool PiFinderMountBridge::Disconnect()
{
    m_client->disconnectServer();
    return true;
}

void PiFinderMountBridge::TimerHit()
{
    if (!isConnected())
        return;

    if (BridgeModeS[MODE_OFF].s == ISS_ON || !m_client->isReady())
    {
        SetTimer(getCurrentPollingPeriod());
        return;
    }

    double piRA, piDec, mountRA, mountDec;
    if (!m_client->getPiFinderRADE(piRA, piDec) || !m_client->getMountRADE(mountRA, mountDec))
    {
        SetTimer(getCurrentPollingPeriod());
        return;
    }

    const double drift = angularSeparationArcmin(piRA, piDec, mountRA, mountDec);
    DriftStatusN[0].value = drift;

    const double threshold = DriftThresholdN[0].value;
    const bool exceeded = drift > threshold;

    if (BridgeModeS[MODE_VERIFY_ALERT].s == ISS_ON)
    {
        DriftStatusNP.s = exceeded ? IPS_ALERT : IPS_OK;
        if (exceeded)
            LOGF_WARN("PiFinder and mount disagree by %.1f arcmin (threshold %.1f).", drift, threshold);
    }
    else if (BridgeModeS[MODE_AUTO_CORRECT].s == ISS_ON)
    {
        DriftStatusNP.s = IPS_OK;
        if (exceeded)
        {
            const char *coordSet = (CorrectionActionS[ACTION_GOTO].s == ISS_ON) ? "TRACK" : "SYNC";
            if (m_client->sendMountCoords(piRA, piDec, coordSet))
                LOGF_INFO("Drift %.1f arcmin exceeded threshold - sent %s to mount.", drift, coordSet);
            else
                LOG_ERROR("Failed to send correction to mount.");
        }
    }

    IDSetNumber(&DriftStatusNP, nullptr);
    SetTimer(getCurrentPollingPeriod());
}

bool PiFinderMountBridge::ISNewSwitch(const char *dev, const char *name, ISState *states, char *names[], int n)
{
    if (dev != nullptr && strcmp(dev, getDeviceName()) == 0)
    {
        if (strcmp(name, BridgeModeSP.name) == 0)
        {
            IUUpdateSwitch(&BridgeModeSP, states, names, n);
            BridgeModeSP.s = IPS_OK;
            IDSetSwitch(&BridgeModeSP, nullptr);
            return true;
        }

        if (strcmp(name, CorrectionActionSP.name) == 0)
        {
            IUUpdateSwitch(&CorrectionActionSP, states, names, n);
            CorrectionActionSP.s = IPS_OK;
            IDSetSwitch(&CorrectionActionSP, nullptr);
            return true;
        }

        if (strcmp(name, ManualTriggerSP.name) == 0)
        {
            IUUpdateSwitch(&ManualTriggerSP, states, names, n);
            const bool wantSync = ManualTriggerS[TRIGGER_SYNC_NOW].s == ISS_ON;
            const bool wantGoto = ManualTriggerS[TRIGGER_GOTO_NOW].s == ISS_ON;

            if (wantSync || wantGoto)
            {
                double piRA, piDec;
                if (!m_client->isReady() || !m_client->getPiFinderRADE(piRA, piDec))
                {
                    LOG_ERROR("Not ready - PiFinder or mount device/properties not available yet.");
                    ManualTriggerSP.s = IPS_ALERT;
                }
                else
                {
                    const char *coordSet = wantGoto ? "TRACK" : "SYNC";
                    if (m_client->sendMountCoords(piRA, piDec, coordSet))
                    {
                        LOGF_INFO("Manual %s sent to mount.", coordSet);
                        ManualTriggerSP.s = IPS_OK;
                    }
                    else
                    {
                        LOG_ERROR("Failed to send manual correction to mount.");
                        ManualTriggerSP.s = IPS_ALERT;
                    }
                }
            }

            IUResetSwitch(&ManualTriggerSP);
            IDSetSwitch(&ManualTriggerSP, nullptr);
            return true;
        }
    }

    return DefaultDevice::ISNewSwitch(dev, name, states, names, n);
}

bool PiFinderMountBridge::ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n)
{
    if (dev != nullptr && strcmp(dev, getDeviceName()) == 0)
    {
        if (strcmp(name, SettingsTP.name) == 0)
        {
            IUUpdateText(&SettingsTP, texts, names, n);
            SettingsTP.s = IPS_OK;
            IDSetText(&SettingsTP, nullptr);
            return true;
        }

        if (strcmp(name, ActiveDeviceTP.name) == 0)
        {
            IUUpdateText(&ActiveDeviceTP, texts, names, n);
            ActiveDeviceTP.s = IPS_OK;
            IDSetText(&ActiveDeviceTP, nullptr);
            return true;
        }
    }

    return DefaultDevice::ISNewText(dev, name, texts, names, n);
}

bool PiFinderMountBridge::ISNewNumber(const char *dev, const char *name, double values[], char *names[], int n)
{
    if (dev != nullptr && strcmp(dev, getDeviceName()) == 0)
    {
        if (strcmp(name, DriftThresholdNP.name) == 0)
        {
            IUUpdateNumber(&DriftThresholdNP, values, names, n);
            DriftThresholdNP.s = IPS_OK;
            IDSetNumber(&DriftThresholdNP, nullptr);
            return true;
        }
    }

    return DefaultDevice::ISNewNumber(dev, name, values, names, n);
}

bool PiFinderMountBridge::saveConfigItems(FILE *fp)
{
    IUSaveConfigText(fp, &SettingsTP);
    IUSaveConfigText(fp, &ActiveDeviceTP);
    IUSaveConfigSwitch(fp, &BridgeModeSP);
    IUSaveConfigSwitch(fp, &CorrectionActionSP);
    IUSaveConfigNumber(fp, &DriftThresholdNP);
    return true;
}

double PiFinderMountBridge::angularSeparationArcmin(double ra1, double dec1, double ra2, double dec2) const
{
    const double toRad = M_PI / 180.0;
    const double ra1Rad = ra1 * 15.0 * toRad;
    const double dec1Rad = dec1 * toRad;
    const double ra2Rad = ra2 * 15.0 * toRad;
    const double dec2Rad = dec2 * toRad;

    double cosSep = sin(dec1Rad) * sin(dec2Rad) + cos(dec1Rad) * cos(dec2Rad) * cos(ra1Rad - ra2Rad);
    cosSep = std::max(-1.0, std::min(1.0, cosSep));

    return acos(cosSep) / toRad * 60.0;
}
