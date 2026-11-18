# Third-party dependencies. g2o and cg2o are expected in install/externals/*
# (scripts/build_externals.sh) and found through CMAKE_PREFIX_PATH, which
# `source scripts/setup_env.sh` sets up.

find_package(Eigen3 3.3 REQUIRED NO_MODULE)
find_package(fmt REQUIRED)
find_package(OpenMP)
find_package(yaml-cpp REQUIRED)
find_package(g2o CONFIG REQUIRED)
find_package(cg2o CONFIG REQUIRED)

# yaml-cpp exports yaml-cpp::yaml-cpp (>= 0.8) or yaml-cpp (older releases)
if(TARGET yaml-cpp::yaml-cpp)
  set(MACC_YAML_TARGET yaml-cpp::yaml-cpp)
else()
  set(MACC_YAML_TARGET yaml-cpp)
endif()

# cg2o exports its public headers via an imported target; never link raw library
# names (that bypasses include dirs / C++ standard requirements).
if(TARGET cg2o::cg2o)
  set(MACC_CG2O_TARGET cg2o::cg2o)
elseif(TARGET cg2o::core)
  set(MACC_CG2O_TARGET cg2o::core)
else()
  message(FATAL_ERROR
    "The selected cg2o package exports neither cg2o::cg2o nor cg2o::core. "
    "Rebuild and install cg2o:  ./scripts/build_externals.sh --cg2o-only --clean")
endif()
if(NOT G2O_LIBRARIES)
  set(G2O_LIBRARIES g2o::core g2o::stuff)
endif()

get_filename_component(_macc_cg2o_cmake_dir "${cg2o_DIR}" ABSOLUTE)
get_filename_component(_macc_g2o_cmake_dir "${g2o_DIR}" ABSOLUTE)
set(MACC_CG2O_CMAKE_DIR "${_macc_cg2o_cmake_dir}")
set(MACC_G2O_CMAKE_DIR "${_macc_g2o_cmake_dir}")

# Optional native IPOPT backend
set(MACC_HAVE_IPOPT OFF)
if(MACC_WITH_IPOPT)
  find_package(IPOPT)
  if(IPOPT_FOUND)
    set(MACC_HAVE_IPOPT ON)
  else()
    message(WARNING "IPOPT not found: building WITHOUT the native IPOPT backend "
                    "(solver 'ipopt' will be unavailable). See cmake/FindIPOPT.cmake for how to install it.")
  endif()
endif()

# Which optional linear solvers does this g2o/cg2o installation provide?
set(MACC_LINEAR_SOLVER_DEFS "")
set(MACC_LINEAR_SOLVER_LIBS "")
macro(_macc_solver_feature target define)
  if(TARGET ${target})
    list(APPEND MACC_LINEAR_SOLVER_DEFS ${define})
    list(APPEND MACC_LINEAR_SOLVER_LIBS ${target})
  endif()
endmacro()
_macc_solver_feature(g2o::solver_cholmod  MACC_HAVE_G2O_CHOLMOD)
_macc_solver_feature(g2o::solver_csparse  MACC_HAVE_G2O_CSPARSE)
_macc_solver_feature(cg2o::solvers_eigen  MACC_HAVE_CG2O_EIGEN)
_macc_solver_feature(cg2o::solver_eigen_umfpack MACC_HAVE_CG2O_UMFPACK)
_macc_solver_feature(cg2o::solver_eigen_pardiso MACC_HAVE_CG2O_PARDISO)
_macc_solver_feature(cg2o::solver_cholmod_fast MACC_HAVE_CG2O_CHOLMOD_FAST)
_macc_solver_feature(cg2o::solver_qdldlt MACC_HAVE_CG2O_QDLDLT)
foreach(_t g2o::solver_dense g2o::solver_eigen g2o::solver_pcg)
  if(TARGET ${_t})
    list(APPEND MACC_LINEAR_SOLVER_LIBS ${_t})
  endif()
endforeach()
