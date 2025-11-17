# ################################################################################
# ########## PiFinder LX200 #############
include_directories("/home/stellarmate/PiFinder_Stellarmate/indi-source/drivers/telescope")

add_library(indi_pifinder_lx200 MODULE
    pifinder_lx200.cpp)

target_compile_definitions(indi_pifinder_lx200 PRIVATE _XOPEN_SOURCE=700)

target_link_libraries(indi_pifinder_lx200 indidriver indilx200 nova)

install(TARGETS indi_pifinder_lx200 LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(FILES
    indi_pifinder_lx200_driver.xml.in
    DESTINATION ${CMAKE_INSTALL_DATADIR}/indi
    COMPONENT Devel)

# ################################################################################