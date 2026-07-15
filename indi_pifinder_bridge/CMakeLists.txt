cmake_minimum_required(VERSION 3.10)
project(indi_pifinder_mount_bridge)

# ################################################################################
# PiFinder Mount Bridge - standalone INDI auxiliary driver
#
# Generic, mount-agnostic coupling between PiFinder's position and whichever
# real INDI mount driver is active. See indi_pifinder_bridge/*.h and
# basic-memory pifinder-stellarmate/00009 for the design.
# ################################################################################

include(GNUInstallDirs)

find_package(PkgConfig REQUIRED)
pkg_check_modules(INDI REQUIRED libindi)

add_executable(indi_pifinder_mount_bridge
    pifinder_mount_bridge.cpp
    pifinder_bridge_client.cpp
)

target_include_directories(indi_pifinder_mount_bridge PRIVATE ${INDI_INCLUDE_DIRS})
target_compile_definitions(indi_pifinder_mount_bridge PRIVATE _XOPEN_SOURCE=700)

target_link_libraries(indi_pifinder_mount_bridge
    indidriver
    indiclient
)

configure_file(indi_pifinder_mount_bridge_driver.xml.in indi_pifinder_mount_bridge_driver.xml @ONLY)

install(TARGETS indi_pifinder_mount_bridge DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/indi_pifinder_mount_bridge_driver.xml DESTINATION ${CMAKE_INSTALL_DATADIR}/indi)
