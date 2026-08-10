cmake_minimum_required(VERSION 3.10)
project(indi_lx200generic_fixed)

# ################################################################################
# Standalone build of the upstream indilib/indi "indi_lx200generic" binary
# (which the "indi_lx200_OnStep" driver is a symlink to - all LX200-family
# drivers share one binary, dispatching on argv[0]), including the mount-type
# detection fix for issue #227 (see diffs/indi_lx200_OnStep_v2.2.2.diff).
#
# Links against the system-installed libindi, same rationale as
# indi_pifinder_bridge/CMakeLists.txt - no full indi monorepo build needed.
# Source file list mirrors upstream's drivers/telescope/CMakeLists.txt
# add_executable(indi_lx200generic ...) target for v2.2.2.
#
# Not built/run by this script directly - see bin/build_indi_onstep_fix.sh,
# which clones the pinned upstream tag, applies the diff, then configures
# this CMakeLists.txt against that checkout.
# ################################################################################

find_package(PkgConfig REQUIRED)
pkg_check_modules(INDI REQUIRED libindi)

if(NOT DEFINED INDI_SRC_DIR)
    message(FATAL_ERROR "INDI_SRC_DIR must be set to the indilib/indi checkout root (see bin/build_indi_onstep_fix.sh)")
endif()

set(SRC_DIR "${INDI_SRC_DIR}/drivers/telescope")

add_executable(indi_lx200generic
    ${SRC_DIR}/lx200driver.cpp
    ${SRC_DIR}/lx200autostar.cpp
    ${SRC_DIR}/lx200_16.cpp
    ${SRC_DIR}/lx200gps.cpp
    ${SRC_DIR}/lx200generic.cpp
    ${SRC_DIR}/lx200telescope.cpp
    ${SRC_DIR}/lx200classic.cpp
    ${SRC_DIR}/lx200gemini.cpp
    ${SRC_DIR}/lx200zeq25.cpp
    ${SRC_DIR}/lx200am5.cpp
    ${SRC_DIR}/lx200gotonova.cpp
    ${SRC_DIR}/lx200pulsar2.cpp
    ${SRC_DIR}/lx200apdriver.cpp
    ${SRC_DIR}/lx200ap_v2.cpp
    ${SRC_DIR}/lx200ap_gtocp2.cpp
    ${SRC_DIR}/lx200fs2.cpp
    ${SRC_DIR}/lx200ss2000pc.cpp
    ${SRC_DIR}/lx200_OnStep.cpp
    ${SRC_DIR}/lx200_OpenAstroTech.cpp
    ${SRC_DIR}/lx200_pegasus_nyx101.cpp
    ${SRC_DIR}/lx200_10micron.cpp
    ${SRC_DIR}/ioptronHC8406.cpp
    ${SRC_DIR}/eq500x.cpp
    ${SRC_DIR}/lx200_esp32go.cpp
)

target_include_directories(indi_lx200generic PRIVATE ${INDI_INCLUDE_DIRS})
target_compile_definitions(indi_lx200generic PRIVATE _XOPEN_SOURCE=600 _POSIX_C_SOURCE=200809L HAVE_LIBNOVA)
target_link_libraries(indi_lx200generic indidriver nova pthread)
