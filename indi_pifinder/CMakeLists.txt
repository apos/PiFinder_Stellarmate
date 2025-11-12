cmake_minimum_required(VERSION 3.5)
project(indi_pifinder)

# find_package(INDI REQUIRED)
include_directories(
    /home/stellarmate/PiFinder_Stellarmate/indi-source/build
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/fpack
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indicore
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/dsp
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/modbus
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indibase
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indibase/stream
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indibase/stream/recorder
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indibase/stream/encoder
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indibase/dsp
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indibase/thread
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indibase/webcam
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indibase/webcam/v4l2_decode
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indibase/pid
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indibase/timer
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indibase/connectionplugins
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indiclientqt
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indiclient
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/eventloop
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indidevice
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indidevice/property
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/alignment
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/alignment/CMakeModules
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/httplib
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/hid
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/indiabstractclient
    /home/stellarmate/PiFinder_Stellarmate/indi-source/libs/sockets
)
link_directories(/home/stellarmate/PiFinder_Stellarmate/indi-source/build/libs/indibase)

set(CMAKE_CXX_STANDARD 17)

add_executable(indi_pifinder_driver pifinder.cpp)
target_link_libraries(indi_pifinder_driver /home/stellarmate/PiFinder_Stellarmate/indi-source/build/libs/indibase/libindidriver.so)
set_target_properties(indi_pifinder_driver PROPERTIES RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/drivers)

configure_file(
    ${CMAKE_CURRENT_SOURCE_DIR}/indi_pifinder_driver.xml.in
    ${CMAKE_CURRENT_BINARY_DIR}/drivers/indi_pifinder_driver.xml
    COPYONLY
)

# install(
#     TARGETS indi_pifinder_driver
#     DESTINATION ${INDI_DRIVERS_PATH}
# )

# install(
#     FILES ${CMAKE_CURRENT_BINARY_DIR}/drivers/indi_pifinder_driver.xml
#     DESTINATION ${INDI_DRIVERS_XML_PATH}
# )