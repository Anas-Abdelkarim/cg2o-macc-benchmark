/* Writes the hardware topology of this machine to an XML file:  hwloc_export_xml <file.xml>
 * SPRAL's SSIDS probes /sys and /proc through hwloc at every analyse call (about 0.3 s on WSL). Running
 * macc_run with HWLOC_XMLFILE=<file.xml> HWLOC_THISSYSTEM=1 makes hwloc read this file instead. */
#include <hwloc.h>
int main(int argc, char **argv) {
  hwloc_topology_t t;
  if (argc < 2 || hwloc_topology_init(&t) || hwloc_topology_load(t)) return 2;
  return hwloc_topology_export_xml(t, argv[1], 0) ? 1 : 0;
}
