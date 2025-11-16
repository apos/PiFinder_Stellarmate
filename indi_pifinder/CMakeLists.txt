cmake_minimum_required(VERSION 3.5)
project(indi_pifinder_lx200 CXX)

find_package(INDI 1.9.0 REQUIRED)
find_package(Libnova REQUIRED)

add_library(indi_pifinder_lx200 MODULE pifinder_lx200.cpp)

target_link_libraries(indi_pifinder_lx200 PRIVATE indidriver indilx200 ${LIBNOVA_LIBRARIES})

install(TARGETS indi_pifinder_lx200 LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(FILES indi_pifinder_lx200_driver.xml.in DESTINATION ${CMAKE_INSTALL_DATADIR}/indi)