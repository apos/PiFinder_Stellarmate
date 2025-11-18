cmake_minimum_required(VERSION 3.5)
project(indi_pifinder_lx200)

# ################################################################################
# ########## PiFinder LX200 #############

# Use standard GNU installation directories
include(GNUInstallDirs)

include_directories(
    /home/stellarmate/PiFinder_Stellarmate/indi-source/build
    /home/stellarmate/PiFinder_Stellarmate/indi-source/drivers/telescope
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indi
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indibase
)

add_executable(indi_pifinder_lx200
    pifinder_lx200.cpp
    /home/stellarmate/PiFinder_Stellarmate/indi-source/drivers/telescope/lx200driver.cpp
    /home/stellarmate/PiFinder_Stellarmate/indi-source/drivers/telescope/lx200telescope.cpp)

target_compile_definitions(indi_pifinder_lx200 PRIVATE _XOPEN_SOURCE=700 HAVE_LIBNOVA)

target_link_libraries(indi_pifinder_lx200 indidriver nova)

# Configure the XML file from the template
configure_file(indi_pifinder_lx200_driver.xml.in indi_pifinder_lx200_driver.xml @ONLY)

# Install the driver executable and the configured XML file
install(TARGETS indi_pifinder_lx200 DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/indi_pifinder_lx200_driver.xml DESTINATION ${CMAKE_INSTALL_DATADIR}/indi)

# ###############################################################################