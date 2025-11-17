# ################################################################################
# ########## PiFinder LX200 #############

# Use standard GNU installation directories
include(GNUInstallDirs)

include_directories("/home/stellarmate/PiFinder_Stellarmate/indi-source/drivers/telescope")

add_executable(indi_pifinder_lx200
    pifinder_lx200.cpp)

target_compile_definitions(indi_pifinder_lx200 PRIVATE _XOPEN_SOURCE=700)

target_link_libraries(indi_pifinder_lx200 indidriver indilx200 lx200generic nova)

# Configure the XML file from the template
configure_file(indi_pifinder_lx200_driver.xml.in indi_pifinder_lx200_driver.xml @ONLY)

# Install the driver executable and the configured XML file
install(TARGETS indi_pifinder_lx200 DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/indi_pifinder_lx200_driver.xml DESTINATION ${CMAKE_INSTALL_DATADIR}/indi)

# ###############################################################################