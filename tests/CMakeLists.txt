add_executable(test_nlp_derivatives unit/test_nlp_derivatives.cpp)
target_link_libraries(test_nlp_derivatives PRIVATE macc::nlp)
add_test(NAME nlp_derivatives COMMAND test_nlp_derivatives)

# ---- integration: solvers on the real closed loop (needs g2o, cg2o and IPOPT) ----
if(MACC_HAVE_IPOPT)
  add_executable(test_solver_consistency integration/test_solver_consistency.cpp)
  target_link_libraries(test_solver_consistency PRIVATE macc::experiment)
  target_compile_definitions(test_solver_consistency PRIVATE MACC_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
  add_test(NAME solver_consistency_N3 COMMAND test_solver_consistency 3 60)
  add_test(NAME solver_consistency_N15 COMMAND test_solver_consistency 15 40)
endif()
