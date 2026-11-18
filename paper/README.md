# paper/

* Section VI of the paper is the MACC benchmark reproduced by this repository.
* `Video.mp4` — the video accompanying the paper.
* `analysis/` — the scripts that draw the paper's MACC figures and compute its MACC tables from experiment folders.

## From your runs to the paper's figures and tables

Run the experiments first ([QUICKSTART.md](../QUICKSTART.md), step 5). Then:

```bash
python3 paper/analysis/paper_tables.py                          # Tables IV and V (newest complete fig2 / fig3 runs)
python3 paper/analysis/paper_figures.py                         # Figs. 2, 3, 4, 7 -> results/paper_figures/
```

Each table is printed and saved into the folder it was computed from (`paper_table_iv.txt`, `paper_table_v.txt`,
`paper_table_vii.txt`, each with a `.json`), so every result folder carries its own table. `run_experiment.py fig2` /
`fig3` does this automatically at the end of the run, and also draws the paper's figures into
`<folder>/figures/` as `paper_fig2_macc_vs_bipm.pdf`, `paper_fig3_macc_vs_ipopt.pdf`, `paper_fig4_macc_trajectory.pdf`
(and `paper_fig7_linear_solver_comparison.pdf` for a linear-solvers run). `paper_figures.py` writes them under the
file names of the paper's LaTeX sources (below). Without arguments the newest *complete* folders are used
(N = 3, 15, 30 over the whole driving cycle; `--quick` runs are skipped), and the folder used is printed.

To use particular folders instead:

```bash
python3 paper/analysis/paper_tables.py  --fig2 results/experiments/<fig2 folder> --fig3 results/experiments/<fig3 folder> \
                                        --large results/experiments/<large-scale linear-solvers folder> --json numbers.json
python3 paper/analysis/paper_figures.py --fig2 ... --fig3 ... --linear results/experiments/<linear-solvers folder> \
                                        --out my_figures --only fig2,fig3
```

| paper | file / output | experiment | script |
|---|---|---|---|
| Fig. 2 | `macc_vs_bipm.pdf` | `fig2` | `paper_figures.py` |
| Fig. 3 | `macc_vs_ipopt.pdf` | `fig3` (with `--set ipopt_settings.use_hsl=true` for MA57) | `paper_figures.py` |
| Fig. 4 | `macc_trajectory.pdf` | `fig3`, N = 30 | `paper_figures.py` |
| Fig. 7 | `linear_solver_comparison.pdf` | `linear-solvers --measure converged --horizons 3 30 ...` | `paper_figures.py` |
| Table IV | `<fig2 folder>/paper_table_iv.txt` | `fig2` | `paper_tables.py` (also run automatically) |
| Table V | `<fig3 folder>/paper_table_v.txt`, with the speed-up factors quoted in the text | `fig3` | `paper_tables.py` (also run automatically) |
| Table VII | `<folder>/paper_table_vii.txt` | `linear-solvers --horizons 30000 300000 --measure fixed --max-iter 10 ...` | `paper_tables.py --large` |
| Sec. VI-E | ρ, mean, median | `fig3` | `experiments/convergence_check/` |

Iteration counts, limits and residuals do not depend on the machine; times do (the paper used an Intel Core
i9-12900H). Compare times through the ratios between the solvers.
