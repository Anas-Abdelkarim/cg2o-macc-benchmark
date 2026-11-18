#!/usr/bin/env python3
"""CMake configure-only smoke test with dummy local g2o/cg2o package exports.

No third-party libraries are downloaded or compiled. Does not prove that a
real cg2o revision is ABI/API compatible with MACC, but verifies transitive
include directories and the required C++20 dialect.
"""
from pathlib import Path
import subprocess,json,tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='macc-cmake-test-') as tmp:
  t=Path(tmp); prefix=t/'prefix'; cg2o=prefix/'cg2o'; g2o=prefix/'g2o'
  for p in [prefix/'include',cg2o/'include',g2o/'include']:
    p.mkdir(parents=True, exist_ok=True)
  hdr=cg2o/'include/cg2o/core/base_fixed_sized_edge_eq.h';hdr.parent.mkdir(parents=True);hdr.touch()
  def make(path,txt):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(txt)
  def target(n,inc):
    return f'add_library({n} INTERFACE IMPORTED)\nset_property(TARGET {n} PROPERTY INTERFACE_INCLUDE_DIRECTORIES "{inc}")\n'
  make(prefix/'lib/cmake/Eigen3/Eigen3Config.cmake',target('Eigen3::Eigen',prefix/'include'))
  make(prefix/'lib/cmake/Eigen3/Eigen3ConfigVersion.cmake','set(PACKAGE_VERSION "3.4.0")\nset(PACKAGE_VERSION_COMPATIBLE TRUE)\n')
  make(prefix/'lib/cmake/fmt/fmt-config.cmake',target('fmt::fmt',prefix/'include'))
  make(prefix/'lib/cmake/yaml-cpp/yaml-cpp-config.cmake',target('yaml-cpp',prefix/'include'))
  make(g2o/'lib/cmake/g2o/g2oConfig.cmake',target('g2o::core',g2o/'include')+target('g2o::stuff',g2o/'include'))
  make(cg2o/'lib/cmake/cg2o/cg2oConfig.cmake',target('cg2o::core',cg2o/'include')+'add_library(cg2o::cg2o INTERFACE IMPORTED)\nset_property(TARGET cg2o::cg2o PROPERTY INTERFACE_LINK_LIBRARIES cg2o::core)\n')
  args=['cmake','-S',str(root),'-B',str(t/'build'),'-G','Ninja',
    '-Dg2o_DIR='+str(g2o/'lib/cmake/g2o'),'-Dcg2o_DIR='+str(cg2o/'lib/cmake/cg2o'),
    '-DCMAKE_PREFIX_PATH='+str(prefix),'-DMACC_CG2O_PREFIX='+str(cg2o),'-DCMAKE_EXPORT_COMPILE_COMMANDS=ON']
  p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  print('Cmake configure status',p.returncode)
  print('\n'.join(p.stdout.splitlines()[-28:]))
  if p.returncode!=0: raise SystemExit(1)
  cc=json.loads((t/'build/compile_commands.json').read_text())
  flags=next(o['command'] for o in cc if o['file'].endswith('edge_dynamics_d_h.cpp') and 'mpc_space' in o['file'])
  print('Include cg2o prefix:',str(cg2o/'include') in flags)
  print('C++20:', '-std=gnu++20' in flags or '-std=c++20' in flags)
  assert str(cg2o/'include') in flags
  assert ('-std=gnu++20' in flags or '-std=c++20' in flags)
