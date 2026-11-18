#!/usr/bin/env python3
"""Local convergence condition of cg2o at the final iterates exported by export_macc (or the quadrotor exporter).

For every problem (same normalization as cg2o, gradient without factor 2):
    E      = sym(HessL) - H_GN            omitted second-order terms (HessL by central differences)
    N_h    = orthonormal basis of null(J_h)
    Hr     = N_h^T H_p N_h,   Hr_ex = N_h^T (H_p + E) N_h
    nu     = eig(Hr_ex, Hr),  rho = max |1 - nu|      condition: all nu in (0, 2)  <=>  rho < 1
Validation: stationarity of gradL, FD step comparison (exporter), and on a few small problems
rho(I - Jhat^-1 J) of the full dense KKT Jacobians in (X, gamma, lambda, s).

usage: analyze.py --run <benchmark>:<N>:<start>:<export dir> [--run ...] --out <dir> [--full-check 3]
"""
import argparse
import csv
import struct
import sys
from pathlib import Path

import numpy as np
import scipy.linalg as sla


# ------------------------------------------------------------------ reading the exporter's records
def read_records(path):
    """Yields one dict per problem: name -> numpy array (format documented in export_macc.cpp)."""
    with open(path, 'rb') as f:
        while True:
            head = f.read(4)
            if len(head) < 4:
                return
            (count,) = struct.unpack('<i', head)
            rec = {}
            for _ in range(count):
                (ln,) = struct.unpack('<i', f.read(4))
                name = f.read(ln).decode()
                dtype = f.read(1).decode()
                (nd,) = struct.unpack('<i', f.read(4))
                shape = struct.unpack('<' + 'q' * nd, f.read(8 * nd))
                size = int(np.prod(shape)) if nd else 1
                dt = np.float64 if dtype == 'd' else np.int32
                rec[name] = np.frombuffer(f.read(size * dt().itemsize), dtype=dt).reshape(shape)
            yield rec


def dense(rec, name):
    r, c = rec[name + '/shape']
    M = np.zeros((r, c))
    M[rec[name + '/i'], rec[name + '/j']] = rec[name + '/v']
    return M


def read_types(path):
    factors = {}
    for line in Path(path).read_text().splitlines():
        p = line.split()
        if p[0] == 'factor':
            factors[int(p[1])] = (p[2], p[3])
    return factors


def sym(M):
    return 0.5 * (M + M.T)


# ------------------------------------------------------------------ the condition
DEFLATION_TAU = 1e-10   # scaled eigenvalues of Hr below tau * max are treated as numerically null
CLEAN_TOL = 1e-8        # E on (and coupling to) that null space below this (scaled units): deflation is clean


def reduced_condition(H_p, E, J_h):
    """Reduced-form condition with Jacobi scaling and deflation of numerically null directions.

    nu = eig(Hr_ex, Hr) is invariant under congruence, so the pair is scaled by D^-1/2 (.) D^-1/2,
    D = diag(Hr): A = scaled Hr, B = scaled Hr_ex. Directions with eig(A) <= DEFLATION_TAU * max eig(A)
    (span Z) are numerically null: there the Gauss-Newton Jacobian is singular to rounding and nu would be
    rounding noise. nu and rho are computed on the complement U; E on Z (e_null) and the coupling Z-U (e_cross),
    both relative to max eig(A), tell whether the exact Jacobian is equally singular there (clean deflation:
    nothing is approximated in those directions) or not (condition undefined for this problem).
    Returns a dict."""
    N_h = sla.null_space(J_h) if J_h.shape[0] else np.eye(H_p.shape[0])
    Hr = sym(N_h.T @ H_p @ N_h)
    Hr_ex = sym(N_h.T @ (H_p + E) @ N_h)
    d = np.diag(Hr).copy()
    dmax = max(d.max(), 1e-300)
    d[d <= 1e-300 * dmax] = dmax
    Ds = 1.0 / np.sqrt(d)
    A = sym(Ds[:, None] * Hr * Ds[None, :])
    B = sym(Ds[:, None] * Hr_ex * Ds[None, :])
    ev, Q = np.linalg.eigh(A)
    amax = max(ev.max(), 1e-300)
    reg = ev > DEFLATION_TAU * amax
    U, Z = Q[:, reg], Q[:, ~reg]
    nu, V = sla.eigh(U.T @ B @ U, np.diag(ev[reg]))
    worst = int(np.argmax(np.abs(1.0 - nu)))
    w = N_h @ (Ds * (U @ V[:, worst]))          # w^T Hr w = 1 in the original variables
    Es = B - A
    e_null = float(np.abs(np.linalg.eigvalsh(sym(Z.T @ Es @ Z))).max() / amax) if Z.shape[1] else 0.0
    e_cross = float(np.linalg.norm(Z.T @ Es @ U, 2) / amax) if Z.shape[1] else 0.0
    return dict(nu=nu, rho=float(np.max(np.abs(1.0 - nu))), w=w, rel_min=float(ev.min() / amax),
                null_dim=N_h.shape[1], deflated=int((~reg).sum()), e_null=e_null, e_cross=e_cross,
                clean=bool(max(e_null, e_cross) <= CLEAN_TOL))


def full_rho(HessL, H_GN, J_h, J_g, lam, s):
    """rho(I - Jhat^-1 J) with rows [stationarity; h; g + s; s*lambda] in (X, gamma, lambda, s)."""
    n, me, mi = HessL.shape[0], J_h.shape[0], J_g.shape[0]
    def jac(H):
        K = np.zeros((n + me + 2 * mi,) * 2)
        x, ga, la, sl = slice(0, n), slice(n, n + me), slice(n + me, n + me + mi), slice(n + me + mi, None)
        K[x, x] = H
        K[x, ga] = J_h.T
        K[x, la] = J_g.T
        K[ga, x] = J_h
        K[la, x] = J_g
        K[la, sl] = np.eye(mi)
        K[sl, la] = np.diag(s)
        K[sl, sl] = np.diag(lam)
        return K
    J, Jhat = jac(HessL), jac(H_GN)
    M = np.eye(J.shape[0]) - np.linalg.solve(Jhat, J)
    return float(np.max(np.abs(np.linalg.eigvals(M)))), float(np.linalg.cond(Jhat))


# ------------------------------------------------------------------ main
def J_g_of(rec):
    return dense(rec, 'J_g')


def condition_metrics(rec, factors):
    """rho, nu and the attribution of E to factor types for one exported problem.
    factors: {type id: (kind, name)}."""
    H_GN, H_p, J_h = dense(rec, 'H_GN'), dense(rec, 'H_p'), dense(rec, 'J_h')
    HessL = sym(dense(rec, 'HessL'))
    E = HessL - H_GN
    R = reduced_condition(H_p, E, J_h)
    nu, rho, w = R['nu'], R['rho'], R['w']
    # contribution of each factor type to (nu - 1) at the extreme eigenvector: w^T E_t w (w^T Hr w = 1)
    contrib = {}
    for t, (kind, name) in factors.items():
        if f'HessL_type/{t}/shape' not in rec:
            continue
        Et = sym(dense(rec, f'HessL_type/{t}'))
        if f'H_GN_type/{t}/shape' in rec:
            Et = Et - dense(rec, f'H_GN_type/{t}')
        v = float(w @ Et @ w)
        if v != 0.0:
            contrib[name] = v
    dom = max(contrib, key=lambda q: abs(contrib[q])) if contrib else ''
    total = sum(abs(v) for v in contrib.values()) or 1.0
    # consistency of gradL with cg2o's own iteration: the next Gauss-Newton step from the exported iterate,
    # built from exactly these residuals, must be at the level of the stopping tolerance
    lam, s, g, h = rec['lambda'], rec['s'], rec['g'], rec['h']
    kappa = float(np.ravel(rec['kappa'])[0])
    rhs = -(rec['gradL'] + J_g_of(rec).T @ ((1.0 / kappa + lam * g) / s))
    n, me = H_p.shape[0], J_h.shape[0]
    K = np.block([[H_p, J_h.T], [J_h, np.zeros((me, me))]])
    step = np.linalg.solve(K, np.concatenate([rhs, -h]))[:n]
    # sign / normalization test: the same residual with a wrong convention (-lambda, -gamma, cost x2, x0.5)
    Jg, gam = J_g_of(rec), rec['gamma']
    gc = rec['gradL'] - J_h.T @ gam - Jg.T @ lam
    wrong = [gc + J_h.T @ gam - Jg.T @ lam, gc - J_h.T @ gam + Jg.T @ lam,
             2 * gc + J_h.T @ gam + Jg.T @ lam, 0.5 * gc + J_h.T @ gam + Jg.T @ lam]
    best_wrong = min(float(np.abs(v).max()) for v in wrong)
    return dict(rho=rho, hr_deflated=R['deflated'], hr_deflation_clean=int(R['clean']), hr_E_null=R['e_null'],
                hr_E_cross=R['e_cross'], hr_scaled_rel_min=R['rel_min'], hr_singular=int(not R['clean']),
                newton_step_inf=float(np.abs(step).max()), newton_decrement=float(abs(rhs @ step)),
                stationarity_vs_wrong_convention=float(np.abs(rec['gradL']).max()) / max(best_wrong, 1e-300), nu_min=float(nu.min()), nu_max=float(nu.max()), null_dim=int(R['null_dim']), E_norm_rel=float(np.linalg.norm(E) / max(np.linalg.norm(H_p), 1e-300)),
                dominant_E_type=dom, dominant_E_share=abs(contrib.get(dom, 0.0)) / total,
                E_contributions=';'.join(f'{q}={v:.3e}' for q, v in
                                         sorted(contrib.items(), key=lambda kv: -abs(kv[1]))))


def analyze_run(bench, N, start, d, rows, full_checks, n_full):
    d = Path(d)
    meta = {int(r['k']): r for r in csv.DictReader(open(d / 'problems.csv'))}
    factors = read_types(d / 'types.txt')
    for rec in read_records(d / 'matrices.bin'):
        k = int(rec['k'][0])
        m = meta[k]
        c = condition_metrics(rec, factors)
        stat = float(m['stationarity_inf'])
        scale = float(m['gradL_scale']) or 1.0
        rows.append(dict(
            benchmark=bench, N=N, start=start, problem_id=k, iterations=int(m['iterations']),
            converged=int(m['converged']), hit_limit=int(m['hit_limit']), stationarity_inf=stat,
            stationarity_rel=stat / scale, kappa=float(m['kappa']), **c,
            fd_rel_E_5_vs_7=float(m['fd_rel_E_5_vs_7']), fd_rel_5_vs_6=float(m['fd_rel_5_vs_6']),
            fd_rel_7_vs_6=float(m['fd_rel_7_vs_6']), assembled_rel_diff=m['assembled_rel_diff'],
            iterations_match_paper=(m['ref_iterations'] == '' or int(m['ref_iterations']) == int(m['iterations']))))
    # dense full-KKT check on the converged problems with the largest rho (second pass)
    if n_full > 0:
        mine = [r for r in rows if r['benchmark'] == bench and r['N'] == N and r['start'] == start
                and r['converged'] and not r['hit_limit']]
        pick = {r['problem_id']: r['rho'] for r in sorted(mine, key=lambda r: -r['rho'])[:n_full]}
        for rec in read_records(d / 'matrices.bin'):
            k = int(rec['k'][0])
            if k not in pick:
                continue
            H_GN, J_h, J_g = dense(rec, 'H_GN'), dense(rec, 'J_h'), dense(rec, 'J_g')
            rf, cond = full_rho(sym(dense(rec, 'HessL')), H_GN, J_h, J_g, rec['lambda'], rec['s'])
            full_checks.append(dict(benchmark=bench, N=N, start=start, problem_id=k, rho_reduced=pick[k],
                                    rho_full=rf, abs_diff=abs(rf - pick[k]), cond_Jhat=cond))


def load_csv_rows(d):
    """rows and full-KKT checks as written by write_outputs, with their types restored."""
    ints = {'N', 'iterations', 'converged', 'hit_limit', 'null_dim', 'usable', 'hr_singular', 'hr_deflated', 'hr_deflation_clean'}
    def conv(k, v):
        if k in ints:
            return int(float(v))
        if k == 'iterations_match_paper':
            return v == 'True'
        if k in ('benchmark', 'start', 'problem_id', 'dominant_E_type', 'E_contributions', 'flight_mode',
                 'assembled_rel_diff'):
            return v
        try:
            return float(v)
        except ValueError:
            return v
    rows = [{k: conv(k, v) for k, v in r.items()} for r in csv.DictReader(open(d / 'convergence_condition.csv'))]
    checks = []
    if (d / 'full_kkt_check.csv').exists():
        checks = [{k: conv(k, v) for k, v in r.items()} for r in csv.DictReader(open(d / 'full_kkt_check.csv'))]
    return rows, checks


def regular(r):
    """converged, not at the iteration limit, and a regular reduced Gauss-Newton matrix"""
    return bool(r['converged']) and not r['hit_limit'] and not r.get('hr_singular', 0)


def pct(a, q):
    return float(np.percentile(a, q)) if len(a) else float('nan')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--run', action='append', default=[], help='<benchmark>:<N>:<start>:<export dir>')
    ap.add_argument('--from-csv', default='', help='rebuild summary and report from convergence_condition.csv '
                    'and full_kkt_check.csv in this directory (no recomputation)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--full-check', type=int, default=3, help='problems per run for the dense full-KKT check')
    ap.add_argument('--full-check-benchmarks', default='macc:3', help='comma list of benchmark:N for that check')
    a = ap.parse_args()
    out = Path(a.out)
    if a.from_csv:
        rows, checks = load_csv_rows(Path(a.from_csv))
        write_outputs(rows, checks, out)
        return
    out.mkdir(parents=True, exist_ok=True)
    allowed = set(a.full_check_benchmarks.split(','))
    rows, checks = [], []
    for spec in a.run:
        bench, N, start, d = spec.split(':', 3)
        n_full = a.full_check if f'{bench}:{N}' in allowed else 0
        print(f'analyzing {bench} N={N} {start}: {d}', file=sys.stderr)
        analyze_run(bench, int(N), start, d, rows, checks, n_full)

    write_outputs(rows, checks, out)



def write_outputs(rows, checks, out):
    """convergence_condition.csv, full_kkt_check.csv, summary.csv and report.md."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cols = ['benchmark', 'N', 'start', 'problem_id', 'iterations', 'converged', 'hit_limit', 'rho', 'nu_min',
            'nu_max', 'hr_singular', 'hr_deflated', 'hr_deflation_clean', 'hr_E_null', 'hr_E_cross', 'hr_scaled_rel_min', 'stationarity_inf', 'stationarity_rel', 'newton_step_inf', 'newton_decrement',
            'stationarity_vs_wrong_convention', 'kappa', 'null_dim', 'E_norm_rel',
            'dominant_E_type', 'dominant_E_share', 'E_contributions', 'fd_rel_E_5_vs_7', 'fd_rel_5_vs_6',
            'fd_rel_7_vs_6', 'assembled_rel_diff', 'iterations_match_paper']
    with open(out / 'convergence_condition.csv', 'w', newline='') as f:
        extra = [k for k in (rows[0] if rows else {}) if k not in cols]
        w = csv.DictWriter(f, fieldnames=cols + extra)
        w.writeheader()
        w.writerows(rows)
    with open(out / 'full_kkt_check.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['benchmark', 'N', 'start', 'problem_id', 'rho_reduced', 'rho_full',
                                          'abs_diff', 'cond_Jhat'])
        w.writeheader()
        w.writerows(checks)
    
    # ---------------- summary
    groups = sorted({(r['benchmark'], r['N'], r['start']) for r in rows})
    summ = []
    for g in groups:
        rs = [r for r in rows if (r['benchmark'], r['N'], r['start']) == g]
        ok = [r for r in rs if regular(r)]
        bad = [r for r in rs if not (r['converged'] and not r['hit_limit'])]
        sing = [r for r in rs if r['converged'] and not r['hit_limit'] and r.get('hr_singular', 0)]
        deflated = [r for r in ok if r.get('hr_deflated', 0)]
        rho = np.array([r['rho'] for r in ok])
        summ.append(dict(benchmark=g[0], N=g[1], start=g[2], problems=len(rs), converged=len(ok),
                         limit_or_unconverged=len(bad), not_clean_deflation=len(sing), with_deflated_directions=len(deflated),
                         rho_max=float(rho.max()) if len(rho) else float('nan'),
                         rho_median=float(np.median(rho)) if len(rho) else float('nan'), rho_p95=pct(rho, 95),
                         rho_ge_1=int((rho >= 1).sum()),
                         nu_min=float(min(r['nu_min'] for r in ok)) if ok else float('nan'),
                         nu_max=float(max(r['nu_max'] for r in ok)) if ok else float('nan'),
                         stationarity_rel_max=float(max(r['stationarity_rel'] for r in ok)) if ok else float('nan'),
                         rho_max_limit_solves=float(max(r['rho'] for r in bad)) if bad else float('nan'),
                         rho_ge_1_limit_solves=sum(r['rho'] >= 1 for r in bad)))
    with open(out / 'summary.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0].keys()))
        w.writeheader()
        w.writerows(summ)
    
    # ---------------- report
    ok_all = [r for r in rows if regular(r)]
    L = ['# Local convergence condition of cg2o at the computed solutions', '',
         'Condition: all generalized eigenvalues nu of (N_h^T (H_p+E) N_h, N_h^T H_p N_h) in (0, 2), i.e. '
         'rho = max|1 - nu| < 1. E = HessL - H_GN, HessL by central differences of the Lagrangian gradient '
         '(cg2o normalization) with the multipliers fixed. Statistics use only solves that met the stopping '
         'tests (numerically null directions of Hr deflated, see below); solves at the iteration limit (or not '
         'converged) and solves whose deflation is not clean are listed separately.', '',
         '## Summary (converged solves)', '',
         '| Benchmark | N | Start | Problems | In statistics | Not clean | Limit / not conv. | rho max | rho median | rho P95 | rho >= 1 | nu min | nu max |',
         '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for s in summ:
        L.append(f"| {s['benchmark']} | {s['N']} | {s['start']} | {s['problems']} | {s['converged']} | "
                 f"{s['not_clean_deflation']} | {s['limit_or_unconverged']} | {s['rho_max']:.3g} | {s['rho_median']:.3g} | {s['rho_p95']:.3g} | {s['rho_ge_1']} | "
                 f"{s['nu_min']:.4g} | {s['nu_max']:.4g} |")
    L += ['', '## Solves at the iteration limit or not converged (not in the statistics above)', '']
    bad = [r for r in rows if not (r['converged'] and not r['hit_limit'])]
    if bad:
        L += ['| Benchmark | N | Start | Problem | Iterations | Converged | rho | nu min | nu max | stationarity (rel.) |',
              '|---|---|---|---|---|---|---|---|---|---|']
        for r in bad:
            L.append(f"| {r['benchmark']} | {r['N']} | {r['start']} | {r['problem_id']} | {r['iterations']} | "
                     f"{r['converged']} | {r['rho']:.3g} | {r['nu_min']:.3g} | {r['nu_max']:.3g} | "
                     f"{r['stationarity_rel']:.2e} |")
    else:
        L.append('None.')
    sing = [r for r in rows if r['converged'] and not r['hit_limit'] and r.get('hr_singular', 0)]
    defl = [r for r in rows if regular(r) and r.get('hr_deflated', 0)]
    L += ['', '## Numerically null directions of the reduced Gauss-Newton matrix', '',
          f'nu is invariant under congruence, so Hr and Hr_ex are Jacobi-scaled (D^-1/2 . D^-1/2, D = diag(Hr)). '
          f'Directions with scaled eigenvalue <= {DEFLATION_TAU:g} x max are numerically null (the Gauss-Newton '
          f'Jacobian is singular there to rounding, and nu would be rounding noise); nu and rho are computed on the '
          f'complement. The deflation is clean when E restricted to those directions and their coupling to the rest '
          f'are <= {CLEAN_TOL:g} (scaled units): then the exact Jacobian is equally singular there and nothing is '
          f'approximated in those directions. Clean cases stay in the statistics; others are listed below.', '']
    if defl:
        dn = np.array([r['hr_deflated'] for r in defl])
        en = np.array([max(r['hr_E_null'], r['hr_E_cross']) for r in defl])
        L.append(f"{len(defl)} of {len(ok_all)} solves in the statistics have deflated directions (median {np.median(dn):.0f}, "
                 f"max {dn.max()}); largest E on / coupling to them: {en.max():.1e}.")
    else:
        L.append('No solve in the statistics has numerically null directions.')
    sing = [r for r in rows if r['converged'] and not r['hit_limit'] and r.get('hr_singular', 0)]
    L += ['', 'Converged solves where the deflation is not clean (condition undefined; not in the statistics):', '']
    if sing:
        L += ['| Benchmark | N | Start | Problem | Iterations | deflated dirs | E on null / coupling | rho on complement | dominant factor type in E |',
              '|---|---|---|---|---|---|---|---|---|']
        for r in sorted(sing, key=lambda r: -max(r['hr_E_null'], r['hr_E_cross']))[:40]:
            L.append(f"| {r['benchmark']} | {r['N']} | {r['start']} | {r['problem_id']} | {r['iterations']} | "
                     f"{r['hr_deflated']} | {r['hr_E_null']:.1e} / {r['hr_E_cross']:.1e} | {r['rho']:.3g} | "
                     f"{r['dominant_E_type']} |")
        if len(sing) > 40:
            L.append(f"\n({len(sing)} in total; all in convergence_condition.csv, column hr_singular.)")
    else:
        L.append('None.')
    L += ['', '## Validation', '']
    ok = [r for r in rows if regular(r)]
    if ok:
        st = np.array([r['stationarity_rel'] for r in ok])
        sa = np.array([r['stationarity_inf'] for r in ok])
        ns = np.array([r['newton_step_inf'] for r in ok])
        nd = np.array([r['newton_decrement'] for r in ok])
        wc = np.array([r['stationarity_vs_wrong_convention'] for r in ok])
        L.append(f"a) Stationarity at converged iterates: ||gradL||_inf max {sa.max():.2e}, median {np.median(sa):.2e}; "
                 f"relative to the largest single gradient term: max {st.max():.2e}, median {np.median(st):.2e}. "
                 f"Sign/normalization test: the same residual with -lambda, -gamma, or the cost gradient x2 or x0.5 "
                 f"is larger in every problem; ||gradL|| / (smallest wrong-convention residual) max {wc.max():.1e}, "
                 f"median {np.median(wc):.1e}, i.e. the cg2o convention is at least {1 / wc.max():.0f} times closer to "
                 f"stationarity than any wrong one. The Gauss-Newton step that cg2o would take next from the exported "
                 f"iterate (built from these residuals) has Newton decrement |b^T dX| median {np.median(nd):.1e}, "
                 f"P95 {np.percentile(nd, 95):.1e}, max {nd.max():.1e}, and ||dX||_inf median {np.median(ns):.1e}, "
                 f"max {ns.max():.1e}: the residual is the convergence error left when the stopping tests were met "
                 f"(they are evaluated on the step taken before, so this next-step decrement is a consistency check, "
                 f"not the stopping quantity itself).")
        f57 = np.array([r['fd_rel_E_5_vs_7'] for r in ok])
        f56 = np.array([r['fd_rel_5_vs_6'] for r in ok])
        f76 = np.array([r['fd_rel_7_vs_6'] for r in ok])
        L.append(f"b) Finite differences: ||HessL(1e-5) - HessL(1e-6)||_F / ||HessL|| max {f56.max():.2e}; "
                 f"||HessL(1e-7) - HessL(1e-6)|| / ||HessL|| max {f76.max():.2e}; "
                 f"||E(1e-5) - E(1e-7)||_F / ||E(1e-6)||_F median {np.median(f57):.2e}, max {f57.max():.2e}.")
        rho_ok = np.array([r['rho'] for r in ok])
        L.append('   (rho with the step 1e-6 is used throughout.)')
    if checks:
        dmax = max(c['abs_diff'] for c in checks)
        L.append(f"c) Full dense KKT Jacobians, rho(I - Jhat^-1 J) vs reduced form on {len(checks)} problems: "
                 f"max |difference| {dmax:.2e}.")
        L += ['', '| Benchmark | N | Problem | rho reduced | rho full | |diff| | cond(Jhat) |', '|---|---|---|---|---|---|---|']
        for c in checks:
            L.append(f"| {c['benchmark']} | {c['N']} | {c['problem_id']} | {c['rho_reduced']:.10f} | "
                     f"{c['rho_full']:.10f} | {c['abs_diff']:.1e} | {c['cond_Jhat']:.1e} |")
    asm = [float(r['assembled_rel_diff']) for r in rows if r['assembled_rel_diff'] not in ('', 'nan')]
    if asm:
        L.append(f"\nH_p (H_GN + J_g^T S^-1 Lambda J_g from cg2o's edge Jacobians) vs the Hessian assembled by cg2o's "
                 f"block solver (written with 9 decimals) on {len(asm)} problems: max relative difference {max(asm):.1e}.")
    mism = [r for r in rows if not r['iterations_match_paper']]
    L.append(f"\nReplay: {len(rows) - len(mism)} of {len(rows)} solves have the iteration count of the paper run.")
    fails = [r for r in ok if r['rho'] >= 1]
    L += ['', '## Problems where the condition fails (converged solves)', '']
    if fails:
        L += ['| Benchmark | N | Start | Problem | rho | nu min | nu max | dominant factor type in E (share) | contributions w^T E_t w |',
              '|---|---|---|---|---|---|---|---|---|']
        for r in sorted(fails, key=lambda r: -r['rho'])[:50]:
            L.append(f"| {r['benchmark']} | {r['N']} | {r['start']} | {r['problem_id']} | {r['rho']:.4g} | "
                     f"{r['nu_min']:.4g} | {r['nu_max']:.4g} | {r['dominant_E_type']} ({r['dominant_E_share']:.0%}) | "
                     f"{r['E_contributions']} |")
    else:
        L.append('None: the condition holds at every converged solve.')
    # which factor types dominate E at the worst problems overall
    L += ['', '## Factor types dominating E at the extreme eigenvector', '']
    for g in groups:
        rs = [r for r in ok if (r['benchmark'], r['N'], r['start']) == g]
        if not rs:
            continue
        cnt = {}
        for r in rs:
            cnt[r['dominant_E_type']] = cnt.get(r['dominant_E_type'], 0) + 1
        top = ', '.join(f'{k} {v}' for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])[:4])
        worst = max(rs, key=lambda r: r['rho'])
        L.append(f"- {g[0]} N={g[1]} {g[2]}: dominant type (count of problems): {top}. Worst problem "
                 f"{worst['problem_id']}: rho {worst['rho']:.4g}, {worst['E_contributions']}")
    (out / 'report.md').write_text('\n'.join(L) + '\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
