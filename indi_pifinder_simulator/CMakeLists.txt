cmake_minimum_required(VERSION 3.10)
project(indi_pifinder_simulator)

# ################################################################################
# PiFinder Simulator - standalone INDI telescope device
#
# A precisely, manually settable "sky truth" position for testing Mount
# Bridge's Auto-correct/Verify-Alert modes without a real mount or clear sky -
# see basic-memory pifinder-stellarmate/00164 and indi_pifinder_simulator/
# pifinder_simulator.h for the design. Not a copy of INDI's own stock
# Telescope Simulator (that remains, unmodified, the *mount* side).
#
# Links directly against the system's libindi, already installed via the OS
# package manager - same standalone-build rationale as indi_pifinder/ and
# indi_pifinder_bridge/ (see basic-memory pifinder-stellarmate/00012).
# ################################################################################

include(GNUInstallDirs)

find_package(PkgConfig REQUIRED)
pkg_check_modules(INDI REQUIRED libindi)
# 2026-09-01: for picking a real, currently-above-horizon default position
# via PiFinder's own /api/nearby_bright_stars at Connect() time - see that
# function's own comment in pifinder_simulator.cpp for why a compiled-in
# fixed default was unsafe.
pkg_check_modules(CURL REQUIRED libcurl)
pkg_check_modules(NLOHMANN_JSON REQUIRED nlohmann_json)

add_executable(indi_pifinder_simulator pifinder_simulator.cpp)

target_include_directories(indi_pifinder_simulator PRIVATE ${INDI_INCLUDE_DIRS} ${CURL_INCLUDE_DIRS} ${NLOHMANN_JSON_INCLUDE_DIRS})
target_compile_definitions(indi_pifinder_simulator PRIVATE _XOPEN_SOURCE=700)

target_link_libraries(indi_pifinder_simulator
    indidriver
    ${CURL_LIBRARIES}
)

configure_file(indi_pifinder_simulator_driver.xml.in indi_pifinder_simulator_driver.xml @ONLY)

install(TARGETS indi_pifinder_simulator DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/indi_pifinder_simulator_driver.xml DESTINATION ${CMAKE_INSTALL_DATADIR}/indi)
