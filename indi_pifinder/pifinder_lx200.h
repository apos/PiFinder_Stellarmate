#pragma once

#include "lx200telescope.h"
#include "indilogger.h"

#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>

class PiFinder : public LX200Telescope
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
    virtual bool Handshake() override;
    void Close();
    bool SendCommand(const char *cmd, char *response, int max_len);
    virtual bool ReadScopeStatus() override;

private:
    int pifinder_fd = -1;

    // INDI Properties for Horizontal Coordinates (not provided by LX200Telescope)
    INumberVectorProperty HorizontalCoordinatesNP;
    INumber HorizontalCoordinatesN[2];
};