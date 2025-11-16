# ################################################################################
# ########## PiFinder LX200 #############
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/..)

add_executable(indi_pifinder_lx200
    pifinder_lx200.cpp)

target_compile_definitions(indi_pifinder_lx200 PRIVATE _XOPEN_SOURCE=700)

target_link_libraries(indi_pifinder_lx200 indidriver indilx200 nova)

install(TARGETS indi_pifinder_lx200 RUNTIME DESTINATION bin)

# ################################################################################