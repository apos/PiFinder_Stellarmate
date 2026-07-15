cmake_minimum_required(VERSION 3.5)
project(indi_pifinder_lx200)

# ################################################################################
# PiFinder LX200 - standalone INDI driver
#
# Links directly against the system's libindi (libindilx200, libindidriver),
# already installed via the OS package manager. No INDI source checkout, no
# full INDI build required - unlike the old lx200generic fat-binary approach
# this replaces (see basic-memory pifinder-stellarmate/00008 for history).
# ################################################################################

include(GNUInstallDirs)

find_package(PkgConfig REQUIRED)
pkg_check_modules(INDI REQUIRED libindi)

add_executable(indi_pifinder_lx200 lx200_pifinder.cpp)

target_include_directories(indi_pifinder_lx200 PRIVATE
    ${INDI_INCLUDE_DIRS}
    ${INDI_INCLUDE_DIRS}/mounts
)

target_compile_definitions(indi_pifinder_lx200 PRIVATE _XOPEN_SOURCE=700 HAVE_LIBNOVA)

target_link_libraries(indi_pifinder_lx200
    indidriver
    indilx200
    nova
)

configure_file(indi_pifinder_lx200_driver.xml.in indi_pifinder_lx200_driver.xml @ONLY)

install(TARGETS indi_pifinder_lx200 DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/indi_pifinder_lx200_driver.xml DESTINATION ${CMAKE_INSTALL_DATADIR}/indi)
