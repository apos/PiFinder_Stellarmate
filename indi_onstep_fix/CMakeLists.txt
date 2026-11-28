cmake_minimum_required(VERSION 3.10)
project(indi_lx200generic_fixed)

# ################################################################################
# Standalone build of the upstream indilib/indi "indi_lx200generic" binary
# (which the "indi_lx200_OnStep" driver is a symlink to - all LX200-family
# drivers share one binary, dispatching on argv[0]), including the mount-type
# detection fix for issue #227 (see diffs/indi_lx200_OnStep.diff).
#
# Links against the system-installed libindi, same rationale as
# indi_pifinder_bridge/CMakeLists.txt - no full indi monorepo build needed.
#
# Not built/run by this script directly - see bin/build_indi_onstep_fix.sh,
# which clones the pinned upstream tag, applies the diff, then configures
# this CMakeLists.txt against that checkout.
# ################################################################################

find_package(PkgConfig REQUIRED)
pkg_check_modules(INDI REQUIRED libindi)

if(NOT DEFINED INDI_SRC_DIR)
    message(FATAL_ERROR "INDI_SRC_DIR must be set to the indilib/indi checkout root (see bin/build_indi_onstep_fix.sh)")
endif()

set(SRC_DIR "${INDI_SRC_DIR}/drivers/telescope")

# The source list is read from the checkout's own build description, so a newer INDI with new LX200 relatives builds unchanged
# (2.2.5 added two files that a hand-kept list for 2.2.2 did not have).
file(READ "${SRC_DIR}/CMakeLists.txt" UPSTREAM)
string(REGEX MATCH "add_executable\\(indi_lx200generic([^)]*)\\)" _found "${UPSTREAM}")
string(REGEX MATCHALL "[A-Za-z0-9_]+\\.cpp" LX200_SOURCES "${CMAKE_MATCH_1}")
if(NOT LX200_SOURCES)
    message(FATAL_ERROR "indi_lx200generic's source list was not found in ${SRC_DIR}/CMakeLists.txt")
endif()
list(TRANSFORM LX200_SOURCES PREPEND "${SRC_DIR}/")

add_executable(indi_lx200generic ${LX200_SOURCES})

target_include_directories(indi_lx200generic PRIVATE ${INDI_INCLUDE_DIRS})
target_compile_definitions(indi_lx200generic PRIVATE _XOPEN_SOURCE=600 _POSIX_C_SOURCE=200809L HAVE_LIBNOVA)
target_link_libraries(indi_lx200generic indidriver nova pthread)
