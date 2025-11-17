# ################################################################################
# ########## PiFinder LX200 #############
include_directories("/home/stellarmate/PiFinder_Stellarmate/indi-source/drivers/telescope")

add_library(indi_pifinder_lx200 MODULE
    pifinder_lx200.cpp)

target_compile_definitions(indi_pifinder_lx200 PRIVATE _XOPEN_SOURCE=700)

target_link_libraries(indi_pifinder_lx200 indidriver indilx200 nova)

# Configure the XML file from the template
configure_file(indi_pifinder_lx200_driver.xml.in indi_pifinder_lx200_driver.xml @ONLY)

# Install the driver library and the configured XML file
install(TARGETS indi_pifinder_lx200 DESTINATION ${INDI_DRIVER_INSTALL_DIR})
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/indi_pifinder_lx200_driver.xml DESTINATION ${INDI_XML_INSTALL_DIR})

# ################################################################################
