cmake_minimum_required(VERSION 3.22)
project(MACC VERSION 2.0.0 LANGUAGES C CXX)


# The binaries find g2o/cg2o/IPOPT shared libraries without sourcing any
# environment script: DT_RPATH (not RUNPATH) is searched transitively, which the
# g2o solver plugins need (they pull in further g2o libraries).
set(CMAKE_BUILD_WITH_INSTALL_RPATH OFF)
set(CMAKE_INSTALL_RPATH_USE_LINK_PATH ON)
set(CMAKE_BUILD_RPATH_USE_ORIGIN ON)
string(APPEND CMAKE_EXE_LINKER_FLAGS " -Wl,--disable-new-dtags")

list(APPEND CMAKE_MODULE_PATH "${PROJECT_SOURCE_DIR}/cmake")

include(MaccOptions)       # build type, user options
include(MaccDependencies)  # Eigen, yaml-cpp, g2o, cg2o, IPOPT, ...

# Everything lives below MACC/include/macc/... and is included as "macc/<module>/<file>".
# No directory of this project is ever added to the *global* include path, so
# headers of different modules can no longer shadow each other (this was the
# cause of the 'MPCParameters was not declared' errors of the old mpc_time/
# mpc_space layout).
add_subdirectory(MACC/src)

# Analysis tool for the local convergence condition (experiments/convergence_check); not part of macc_run.
option(MACC_BUILD_CONVERGENCE_CHECK "Build experiments/convergence_check/export_macc" ON)
if(MACC_BUILD_CONVERGENCE_CHECK)
  add_subdirectory(experiments/convergence_check)
endif()

if(MACC_BUILD_TESTS)
  enable_testing()
  add_subdirectory(tests)
endif()

include(MaccSummary)
