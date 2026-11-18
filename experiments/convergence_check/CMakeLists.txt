# Local-convergence analysis of cg2o (analysis only, does not change any solver or result).
add_executable(export_macc export_macc.cpp)
target_link_libraries(export_macc PRIVATE macc::experiment)
set_target_properties(export_macc PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
