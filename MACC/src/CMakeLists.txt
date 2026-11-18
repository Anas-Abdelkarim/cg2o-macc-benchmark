# ---------------------------------------------------------------------------
# Libraries (static, each in its own namespace macc::)
#
#   macc::core       config (YAML), statistics, tables, run directory / report helpers
#   macc::nlp        solver-independent MACC NLP with exact derivatives
#   macc::model      factor-graph vertices + edges + closed-loop plant (needs g2o/cg2o)
#   macc::solvers    registry of linear solvers
#   macc::cg2o       cg2o backend (ISPD / BIPM / AL)
#   macc::ipopt      native IPOPT backend (or a stub when IPOPT is absent)
#   macc::experiment closed-loop runner and report writer
# ---------------------------------------------------------------------------

set(MACC_INCLUDE_DIR "${PROJECT_SOURCE_DIR}/MACC/include")

function(macc_add_library name)
  add_library(${name} STATIC ${ARGN})
  add_library(macc::${name} ALIAS ${name})
  target_include_directories(${name} PUBLIC $<BUILD_INTERFACE:${MACC_INCLUDE_DIR}>)
  target_compile_features(${name} PUBLIC cxx_std_20)
  target_link_libraries(${name} PRIVATE macc_warnings)
endfunction()

# ---- core ------------------------------------------------------------------
macc_add_library(core core/stats.cpp core/table.cpp core/run_info.cpp)
target_link_libraries(core PUBLIC ${MACC_YAML_TARGET})
target_compile_definitions(core PRIVATE
  MACC_BUILD_TYPE="$<CONFIG>"
  MACC_SOURCE_DIR="${PROJECT_SOURCE_DIR}"
  MACC_G2O_PREFIX_STR="${MACC_G2O_CMAKE_DIR}"
  MACC_CG2O_PREFIX_STR="${MACC_CG2O_CMAKE_DIR}"
  MACC_IPOPT_VERSION_STR="${IPOPT_VERSION}")

# ---- nlp -------------------------------------------------------------------
macc_add_library(nlp nlp/macc_nlp.cpp nlp/problem_data.cpp nlp/evaluation.cpp nlp/structure.cpp)

# ---- model (factor graph) --------------------------------------------------
file(GLOB MACC_EDGE_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/fg/edges/*.cpp")
macc_add_library(model ${MACC_EDGE_SOURCES} mpc/closed_loop.cpp)
target_link_libraries(model PUBLIC ${MACC_CG2O_TARGET} ${G2O_LIBRARIES} Eigen3::Eigen)
if(MACC_NUMERICAL_JACOBIANS)
  target_compile_definitions(model PUBLIC MPC_USE_NUMERICAL_JACOBIANS=1)
else()
  target_compile_definitions(model PUBLIC MPC_USE_NUMERICAL_JACOBIANS=0)
endif()

# ---- linear solvers ----------------------------------------------------------
macc_add_library(solvers solvers/linear_solvers.cpp)
target_link_libraries(solvers PUBLIC ${MACC_CG2O_TARGET} ${G2O_LIBRARIES} Eigen3::Eigen
                                     ${MACC_LINEAR_SOLVER_LIBS})
target_compile_definitions(solvers PRIVATE ${MACC_LINEAR_SOLVER_DEFS})

# ---- backends ----------------------------------------------------------------
macc_add_library(cg2o backends/cg2o/cg2o_controller.cpp)
target_link_libraries(cg2o PUBLIC macc::core macc::nlp macc::model macc::solvers)

if(MACC_HAVE_IPOPT)
  macc_add_library(ipopt backends/ipopt/ipopt_controller.cpp)
  target_link_libraries(ipopt PUBLIC macc::core macc::nlp IPOPT::IPOPT)
  target_compile_definitions(ipopt PRIVATE MACC_IPOPT_VERSION_STR="${IPOPT_VERSION}"
                                           MACC_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
else()
  macc_add_library(ipopt backends/ipopt/ipopt_stub.cpp)
  target_link_libraries(ipopt PUBLIC macc::core macc::nlp)
endif()

# ---- experiment --------------------------------------------------------------
macc_add_library(experiment experiment/setup.cpp experiment/closed_loop.cpp experiment/report.cpp)
target_link_libraries(experiment PUBLIC macc::core macc::nlp macc::model macc::cg2o macc::ipopt
                                        macc::solvers)
if(OpenMP_CXX_FOUND)
  target_link_libraries(experiment PUBLIC OpenMP::OpenMP_CXX)
endif()

# ---- applications -----------------------------------------------------------
add_executable(macc_run apps/macc_run.cpp)
target_link_libraries(macc_run PRIVATE macc::experiment macc_warnings)
target_compile_definitions(macc_run PRIVATE MACC_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
set_target_properties(macc_run PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
