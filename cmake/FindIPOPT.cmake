# FindIPOPT.cmake - locate IPOPT through pkg-config (works for the Ubuntu package
# coinor-libipopt-dev as well as for the copy built by scripts/build_externals/ipopt.sh).
#
# Result:  IPOPT_FOUND, IPOPT_VERSION, imported target IPOPT::IPOPT

find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
  pkg_check_modules(_IPOPT_PC QUIET IMPORTED_TARGET ipopt)
endif()

if(_IPOPT_PC_FOUND)
  set(IPOPT_VERSION "${_IPOPT_PC_VERSION}")
  if(NOT TARGET IPOPT::IPOPT)
    add_library(IPOPT::IPOPT INTERFACE IMPORTED)
    target_link_libraries(IPOPT::IPOPT INTERFACE PkgConfig::_IPOPT_PC)
  endif()
endif()

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(IPOPT
  REQUIRED_VARS IPOPT_VERSION
  VERSION_VAR IPOPT_VERSION
  FAIL_MESSAGE "IPOPT not found. Install it with 'sudo apt install coinor-libipopt-dev' or 'scripts/build_externals.sh --ipopt-only' (then 'source scripts/setup_env.sh').")
