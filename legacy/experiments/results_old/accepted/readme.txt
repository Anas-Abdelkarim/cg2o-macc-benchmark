export PYTHONPATH="/mnt/e/1.PhD/factor_graphs/g2o/ideas/unconstrained/mpc/mpc_space/../lib:/mnt/e/1.PhD/factor_graphs/g2o/ideas/unconstrained/mpc/mpc_space:$PYTHONPATH"


python3 -m results.results_harvesting 260217_1357_AMPL_0_3.bin
python3 -m results.results_harvesting_both 260220_1610_AMPL_0_G2O_ISPD_gn_GN_13_3.bin

python3 real_time_results.py --out /mnt/e/1.PhD/Papers/2025-RAL-IPM_g2o/figure/real_time_results

python3 g2o_vs_ipopt.py --out /mnt/e/1.PhD/Papers/2025-RAL-IPM_g2o/figure/g2o_vs_ipopt

python g2o_vs_ipopt_plot.py --dir path/to/bin/files --out figure


python3 g2o_vs_ipopt_extract.py --dir /mnt/e/1.PhD/factor_graphs/g2o/ideas/unconstrained/mpc/mpc_space/results/data/6/
python3 g2o_vs_ipopt_plot.py --dir /mnt/e/1.PhD/factor_graphs/g2o/ideas/unconstrained/mpc/mpc_space/results/data/6/ --out figure6

 
python3 established_solvers_extract.py \
    --ipopt-folder 0 \
    --knitro-folder 1 \
    --conopt-folder 5 \
    --loqo-folder 6 \
    --minos-folder 7 \
    --snopt-folder 8  \
    --dir ./data/established/ \
    --out ./data/established_results/
    
python3 established_solvers_iterations_plot.py \
    --dir ./data/established_results/ \
    --out ./figures/established_iterations
    
    
python3 g2o_vs_ipopt_extract.py \
    --dir ./data/g2o_vs_ipopt/ \
    
    
python3 g2o_vs_ipopt_plot.py \
    --dir ./data/g2o_vs_ipopt/ \ 
    --out ./figures/g2o_vs_ipopt
    
python3 real_time_results.py \
    --zip ./data/signals_real_time.zip \
    --out /mnt/e/1.PhD/Papers/2025-RAL-IPM_g2o/figure/real_time_results
    
    
python3 closed_loop_failed_extract.py \
    --dir ./data/established/closed_loop_failed 


python3 closed_loop_failed_plot.py \
  --dir ./data/established/closed_loop_failed \
  --files 260306_0209_AMPL_6_30 260306_0252_AMPL_5_30 260306_0327_AMPL_7_30 \
  --labels LOQO CONOPT MINOS \
  --out /mnt/e/1.PhD/Papers/2025-RAL-IPM_g2o/figure/closed_loop_failed \
   --layout horizontal
   
   
   
python3 linear_solver_evaluatio.py \ 
    --out /mnt/e/1.PhD/Papers/2025-RAL-IPM_g2o/figure/real_time_results
    
    
    
python3 g2o_vs_bipm_extract.py --dir ./data/ispd_vs_bipm
python3 g2o_vs_bipm_plot.py --dir ./data/ispd_vs_bipm --out /mnt/e/1.PhD/Papers/2025-RAL-IPM_g2o/figure/g2o_vs_bipm
