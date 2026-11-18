# Build type and user-visible options of MACC.

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
  set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS Debug Release RelWithDebInfo MinSizeRel)
endif()

option(MACC_BUILD_TESTS        "Build the unit / consistency tests"                 ON)
option(MACC_NUMERICAL_JACOBIANS "Let g2o differentiate the factors numerically (slow; for debugging analytic Jacobians)" OFF)
option(MACC_WITH_IPOPT         "Build the native IPOPT backend (needs IPOPT)"       ON)
# Must match the -march=native setting of the installed g2o/cg2o (build_workspace.sh reads it from
# g2o's install stamp). A mismatch changes Eigen's allocator between MACC and g2o: memory allocated
# in MACC code is then freed by g2o with the other allocator (crash in ~JacobianWorkspace with OpenMP).
option(MACC_MARCH_NATIVE       "Compile with -march=native (same as g2o/cg2o)"      OFF)
if(MACC_MARCH_NATIVE AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-march=native)
endif()

# Same warning level for every MACC target (does not touch third-party code).
add_library(macc_warnings INTERFACE)
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(macc_warnings INTERFACE -Wall -Wextra -Wno-unused-parameter)
endif()
