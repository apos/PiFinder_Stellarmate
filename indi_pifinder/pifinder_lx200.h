#pragma once

#include "defaultdevice.h"
#include "indiproperty.h"
#include "indilogger.h"

#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <libnova/julian_day.h>
#include <libnova/transform.h>

class PiFinder : public INDI::DefaultDevice
{
public:
    PiFinder();

    virtual const char *getDefaultName() override;
    virtual bool initProperties() override;
    virtual bool updateProperties() override;
    virtual void ISGetProperties(const char *dev) override;
    virtual bool ISNewSwitch(const char *dev, const char *name, ISState *states, char *names[], int n) override;
    virtual bool ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n) override;
    virtual bool ISNewNumber(const char *dev, const char *name, double *values, char *names[], int n) override;
    virtual bool ISNewBLOB(const char *dev, const char *name, int sizes[], int blobsizes[], char *blobs[], char *formats[], char *names[], int n) override;

protected:
    bool Handshake();
    void Close();
    bool SendCommand(const char *cmd, char *response, int max_len);
    bool ReadScopeStatus();

private:
    int pifinder_fd = -1;

    // INDI Properties
    INDI::PropertySwitch ConnectionSP;
    ISwitch ConnectionS[2];

    INDI::PropertyNumber EquatorialEODNP;
    INumber EquatorialEODN[2];

    INDI::PropertyNumber HorizontalCoordinatesNP;
    INumber HorizontalCoordinatesN[2];
};