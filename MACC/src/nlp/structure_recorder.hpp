#ifndef MACC_SRC_NLP_STRUCTURE_RECORDER_HPP
#define MACC_SRC_NLP_STRUCTURE_RECORDER_HPP

// Sink that records the sparsity pattern of a derivative pass.
// Private to src/nlp; not part of the public headers.

#include <map>
#include <utility>
#include <vector>

namespace macc::nlp::detail {

// Recording sink: maps (i,j) to a unique slot and remembers the call order.
struct Recorder {
  std::map<std::pair<int, int>, int> index;
  std::vector<int> *ri = nullptr, *rj = nullptr, *slot = nullptr;
  void operator()(int i, int j, double) {
    auto key = std::make_pair(i, j);
    auto it = index.find(key);
    int s;
    if (it == index.end()) {
      s = static_cast<int>(ri->size());
      index.emplace(key, s);
      ri->push_back(i);
      rj->push_back(j);
    } else {
      s = it->second;
    }
    slot->push_back(s);
  }
};

} // namespace macc::nlp::detail

#endif // MACC_SRC_NLP_STRUCTURE_RECORDER_HPP
