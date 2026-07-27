"""hmm.py — leichtgewichtiges Gaussian-HMM (reines Python) für die Markt-Regime-Erkennung.

Ersetzt die fixe Schwellen-/Hysterese-Heuristik durch ein **statistisch gelerntes** Zustandsmodell:
K verborgene Zustände emittieren Renditen als Gauß-Verteilungen; ``fit`` schätzt Start-/Übergangs-
Wahrscheinlichkeiten + Mittel/Varianz per **Baum-Welch (EM)** (log-stabil), ``viterbi`` dekodiert den
wahrscheinlichsten Zustandspfad. Die **Übergangs-Persistenz** (diagonal-lastige Init) glättet das
Regime — und Viterbi wählt den aktuellen Zustand global konsistent (kein Flip durch eine einzelne
Ausreißer-Stunde). Dependency-leicht (nur ``math``), deterministisch, testbar. 0 Risiko (read-only).
"""
from __future__ import annotations

import math

NEG_INF = float("-inf")


def _logsumexp(vals: list[float]) -> float:
    m = max(vals)
    if m == NEG_INF:
        return NEG_INF
    return m + math.log(sum(math.exp(v - m) for v in vals))


def _log_gauss(x: float, mu: float, var: float) -> float:
    return -0.5 * (math.log(2.0 * math.pi * var) + (x - mu) ** 2 / var)


def fit(obs: list[float], n_states: int = 3, n_iter: int = 25, tol: float = 1e-4,
        var_floor: float | None = None) -> dict | None:
    """Baum-Welch-Schätzung eines Gaussian-HMM (log-stabil). None bei zu wenig Daten."""
    T = len(obs)
    if T < n_states * 4 or n_states < 2:
        return None
    ov_mean = sum(obs) / T
    ov_var = sum((x - ov_mean) ** 2 for x in obs) / T or 1e-6
    vf = var_floor if var_floor is not None else max(1e-9, 0.01 * ov_var)
    sv = sorted(obs)
    means = [sv[min(T - 1, int((i + 0.5) / n_states * T))] for i in range(n_states)]
    vars_ = [max(vf, ov_var) for _ in range(n_states)]
    start = [1.0 / n_states for _ in range(n_states)]
    trans = [[(0.90 if i == j else 0.10 / (n_states - 1)) for j in range(n_states)] for i in range(n_states)]

    def _logv(p):
        return math.log(p) if p > 0 else NEG_INF

    prev_ll = NEG_INF
    gamma = [[1.0 / n_states] * n_states for _ in range(T)]
    last_ll = NEG_INF
    for _ in range(max(1, n_iter)):
        log_start = [_logv(p) for p in start]
        log_trans = [[_logv(p) for p in row] for row in trans]
        logB = [[_log_gauss(obs[t], means[i], vars_[i]) for i in range(n_states)] for t in range(T)]
        # Forward
        log_alpha = [[NEG_INF] * n_states for _ in range(T)]
        for i in range(n_states):
            log_alpha[0][i] = log_start[i] + logB[0][i]
        for t in range(1, T):
            for j in range(n_states):
                log_alpha[t][j] = _logsumexp([log_alpha[t - 1][i] + log_trans[i][j]
                                              for i in range(n_states)]) + logB[t][j]
        ll = _logsumexp(log_alpha[T - 1])
        last_ll = ll
        # Backward
        log_beta = [[NEG_INF] * n_states for _ in range(T)]
        for i in range(n_states):
            log_beta[T - 1][i] = 0.0
        for t in range(T - 2, -1, -1):
            for i in range(n_states):
                log_beta[t][i] = _logsumexp([log_trans[i][j] + logB[t + 1][j] + log_beta[t + 1][j]
                                             for j in range(n_states)])
        # Posterior gamma
        gamma = [[math.exp(log_alpha[t][i] + log_beta[t][i] - ll) for i in range(n_states)] for t in range(T)]
        # Übergänge (xi) akkumulieren
        new_trans = [[0.0] * n_states for _ in range(n_states)]
        denom = [0.0] * n_states
        for t in range(T - 1):
            terms = [log_alpha[t][i] + log_trans[i][j] + logB[t + 1][j] + log_beta[t + 1][j]
                     for i in range(n_states) for j in range(n_states)]
            norm = _logsumexp(terms)
            for i in range(n_states):
                for j in range(n_states):
                    xi = math.exp(log_alpha[t][i] + log_trans[i][j] + logB[t + 1][j] + log_beta[t + 1][j] - norm)
                    new_trans[i][j] += xi
                    denom[i] += xi
        # Re-Estimation
        start = gamma[0][:]
        for i in range(n_states):
            if denom[i] > 1e-12:
                trans[i] = [new_trans[i][j] / denom[i] for j in range(n_states)]
        for i in range(n_states):
            gsum = sum(gamma[t][i] for t in range(T))
            if gsum > 1e-12:
                mu = sum(gamma[t][i] * obs[t] for t in range(T)) / gsum
                v = sum(gamma[t][i] * (obs[t] - mu) ** 2 for t in range(T)) / gsum
                means[i] = mu
                vars_[i] = max(vf, v)
        if prev_ll != NEG_INF and abs(ll - prev_ll) < tol:
            break
        prev_ll = ll
    return {"n_states": n_states, "start": start, "trans": trans, "means": means, "vars": vars_,
            "post_last": gamma[T - 1][:], "loglik": last_ll}


def viterbi(obs: list[float], model: dict) -> list[int]:
    """Wahrscheinlichster Zustandspfad (MAP) via Viterbi (log-Raum)."""
    T = len(obs)
    K = model["n_states"]
    means, vars_ = model["means"], model["vars"]
    log_start = [math.log(p) if p > 0 else NEG_INF for p in model["start"]]
    log_trans = [[math.log(p) if p > 0 else NEG_INF for p in row] for row in model["trans"]]
    logB = [[_log_gauss(obs[t], means[i], vars_[i]) for i in range(K)] for t in range(T)]
    delta = [[NEG_INF] * K for _ in range(T)]
    psi = [[0] * K for _ in range(T)]
    for i in range(K):
        delta[0][i] = log_start[i] + logB[0][i]
    for t in range(1, T):
        for j in range(K):
            best, arg = NEG_INF, 0
            for i in range(K):
                val = delta[t - 1][i] + log_trans[i][j]
                if val > best:
                    best, arg = val, i
            delta[t][j] = best + logB[t][j]
            psi[t][j] = arg
    last = max(range(K), key=lambda i: delta[T - 1][i])
    path = [0] * T
    path[T - 1] = last
    for t in range(T - 2, -1, -1):
        path[t] = psi[t + 1][path[t + 1]]
    return path


# ===================== Multivariates Gaussian-HMM (diagonale Kovarianz) =====================
# Emission = mehrere unabhängige Gauß-Features (z.B. [Rendite, Volatilität]) — trennt Regimes
# sauberer (ruhiger Aufwärts- vs. volatiler Abwärtsmarkt). Regime-Label nach der RENDITE-Dimension (0).

def _log_gauss_diag(x: list[float], mu: list[float], var: list[float]) -> float:
    s = 0.0
    for d in range(len(x)):
        s += -0.5 * (math.log(2.0 * math.pi * var[d]) + (x[d] - mu[d]) ** 2 / var[d])
    return s


def _sanitize_init(init: dict, n_states: int, D: int, vf: list[float]) -> tuple | None:
    """Prüft/normalisiert ein Warm-Start-Modell (persistiertes Vorgänger-Fit) als EM-Init.
    Wahrscheinlichkeiten werden auf ≥1e-6 geklemmt + renormiert (kein Zustand stirbt an log(0)),
    Varianzen auf den Floor geklemmt. None bei inkompatibler Form."""
    try:
        if int(init.get("n_states", 0)) != n_states or int(init.get("dims", 0)) != D:
            return None
        means = [[float(x) for x in m] for m in init["means"]]
        vars_ = [[max(vf[d], float(v[d])) for d in range(D)] for v in init["vars"]]
        if len(means) != n_states or len(vars_) != n_states:
            return None

        def _norm(row):
            row = [max(1e-6, float(p)) for p in row]
            s = sum(row)
            return [p / s for p in row]

        start = _norm(init["start"])
        trans = [_norm(row) for row in init["trans"]]
        if len(start) != n_states or len(trans) != n_states:
            return None
        return means, vars_, start, trans
    except Exception:
        return None


def fit_mv(obs: list[list[float]], n_states: int = 3, n_iter: int = 25, tol: float = 1e-4,
           init: dict | None = None) -> dict | None:
    """Baum-Welch für ein multivariates Gaussian-HMM mit DIAGONALER Kovarianz (log-stabil).

    **Dual-Init gegen lokale EM-Optima:** gefittet wird ab der deterministischen Quantil-
    Initialisierung UND (falls ``init`` = persistiertes Vorgänger-Modell übergeben) ab dessen
    Parametern (Warm-Start); behalten wird der Lauf mit der höheren Log-Likelihood. Der
    Warm-Start hält zugleich die Zustands-Identität über Re-Fits stabil (Label-Kontinuität)."""
    T = len(obs)
    if T < n_states * 4 or n_states < 2 or not obs:
        return None
    D = len(obs[0])
    col = [[obs[t][d] for t in range(T)] for d in range(D)]
    ov_mean = [sum(col[d]) / T for d in range(D)]
    ov_var = [max(1e-9, sum((v - ov_mean[d]) ** 2 for v in col[d]) / T or 1e-6) for d in range(D)]
    vf = [max(1e-9, 0.01 * ov_var[d]) for d in range(D)]
    # Init 1 (deterministisch): nach Dim 0 (Rendite) in Quantil-Bins, Mittel je Bin/Dim
    order0 = sorted(range(T), key=lambda t: obs[t][0])
    means_q = []
    for i in range(n_states):
        idx = order0[min(T - 1, int((i + 0.5) / n_states * T))]
        means_q.append(list(obs[idx]))
    inits = [(means_q, [list(ov_var) for _ in range(n_states)], [1.0 / n_states] * n_states,
              [[(0.90 if i == j else 0.10 / (n_states - 1)) for j in range(n_states)]
               for i in range(n_states)])]
    if init:
        warm = _sanitize_init(init, n_states, D, vf)
        if warm:
            inits.append(warm)
    best = None
    for means0, vars0, start0, trans0 in inits:
        m = _em_mv(obs, n_states, n_iter, tol, vf, means0, vars0, start0, trans0)
        if best is None or m["loglik"] > best["loglik"]:
            best = m
    return best


def _em_mv(obs: list[list[float]], n_states: int, n_iter: int, tol: float, vf: list[float],
           means0: list, vars0: list, start0: list, trans0: list) -> dict:
    """EIN Baum-Welch-Lauf ab gegebener Initialisierung (log-stabil); Kern von ``fit_mv``."""
    T = len(obs)
    D = len(obs[0])
    means = [list(m) for m in means0]
    vars_ = [list(v) for v in vars0]
    start = list(start0)
    trans = [list(row) for row in trans0]

    def _lv(p):
        return math.log(p) if p > 0 else NEG_INF

    prev_ll, gamma, last_ll = NEG_INF, [[1.0 / n_states] * n_states for _ in range(T)], NEG_INF
    for _ in range(max(1, n_iter)):
        log_start = [_lv(p) for p in start]
        log_trans = [[_lv(p) for p in row] for row in trans]
        logB = [[_log_gauss_diag(obs[t], means[i], vars_[i]) for i in range(n_states)] for t in range(T)]
        log_alpha = [[NEG_INF] * n_states for _ in range(T)]
        for i in range(n_states):
            log_alpha[0][i] = log_start[i] + logB[0][i]
        for t in range(1, T):
            for j in range(n_states):
                log_alpha[t][j] = _logsumexp([log_alpha[t - 1][i] + log_trans[i][j]
                                              for i in range(n_states)]) + logB[t][j]
        last_ll = _logsumexp(log_alpha[T - 1])
        log_beta = [[NEG_INF] * n_states for _ in range(T)]
        for i in range(n_states):
            log_beta[T - 1][i] = 0.0
        for t in range(T - 2, -1, -1):
            for i in range(n_states):
                log_beta[t][i] = _logsumexp([log_trans[i][j] + logB[t + 1][j] + log_beta[t + 1][j]
                                             for j in range(n_states)])
        gamma = [[math.exp(log_alpha[t][i] + log_beta[t][i] - last_ll) for i in range(n_states)] for t in range(T)]
        new_trans = [[0.0] * n_states for _ in range(n_states)]
        denom = [0.0] * n_states
        for t in range(T - 1):
            terms = [log_alpha[t][i] + log_trans[i][j] + logB[t + 1][j] + log_beta[t + 1][j]
                     for i in range(n_states) for j in range(n_states)]
            norm = _logsumexp(terms)
            for i in range(n_states):
                for j in range(n_states):
                    xi = math.exp(log_alpha[t][i] + log_trans[i][j] + logB[t + 1][j] + log_beta[t + 1][j] - norm)
                    new_trans[i][j] += xi
                    denom[i] += xi
        start = gamma[0][:]
        for i in range(n_states):
            if denom[i] > 1e-12:
                trans[i] = [new_trans[i][j] / denom[i] for j in range(n_states)]
        for i in range(n_states):
            gsum = sum(gamma[t][i] for t in range(T))
            if gsum > 1e-12:
                for d in range(D):
                    mu = sum(gamma[t][i] * obs[t][d] for t in range(T)) / gsum
                    v = sum(gamma[t][i] * (obs[t][d] - mu) ** 2 for t in range(T)) / gsum
                    means[i][d] = mu
                    vars_[i][d] = max(vf[d], v)
        if prev_ll != NEG_INF and abs(last_ll - prev_ll) < tol:
            break
        prev_ll = last_ll
    return {"n_states": n_states, "dims": D, "start": start, "trans": trans, "means": means,
            "vars": vars_, "post_last": gamma[T - 1][:], "loglik": last_ll}


def viterbi_mv(obs: list[list[float]], model: dict) -> list[int]:
    T, K = len(obs), model["n_states"]
    means, vars_ = model["means"], model["vars"]
    log_start = [math.log(p) if p > 0 else NEG_INF for p in model["start"]]
    log_trans = [[math.log(p) if p > 0 else NEG_INF for p in row] for row in model["trans"]]
    logB = [[_log_gauss_diag(obs[t], means[i], vars_[i]) for i in range(K)] for t in range(T)]
    delta = [[NEG_INF] * K for _ in range(T)]
    psi = [[0] * K for _ in range(T)]
    for i in range(K):
        delta[0][i] = log_start[i] + logB[0][i]
    for t in range(1, T):
        for j in range(K):
            best, arg = NEG_INF, 0
            for i in range(K):
                val = delta[t - 1][i] + log_trans[i][j]
                if val > best:
                    best, arg = val, i
            delta[t][j] = best + logB[t][j]
            psi[t][j] = arg
    last = max(range(K), key=lambda i: delta[T - 1][i])
    path = [0] * T
    path[T - 1] = last
    for t in range(T - 2, -1, -1):
        path[t] = psi[t + 1][path[t + 1]]
    return path


def classify_mv(obs: list[list[float]], n_states: int = 3, init: dict | None = None) -> dict | None:
    """Multivariates Fit+Decode. Regime-Label nach der RENDITE-Dimension (0); zusätzlich die
    Volatilitäts-Dimension (1) des aktuellen Zustands. ``init`` = persistiertes Vorgänger-Modell
    (Warm-Start, Label-Kontinuität); das gefittete Roh-Modell liegt unter ``model`` in der
    Antwort (zum Persistieren für den nächsten Fit). None bei zu wenig Daten."""
    model = fit_mv(obs, n_states=n_states, init=init)
    if not model:
        return None
    path = viterbi_mv(obs, model)
    cur = path[-1]
    order = sorted(range(n_states), key=lambda i: model["means"][i][0])   # nach Rendite-Mittel
    rank = order.index(cur)
    if n_states == 3:
        label = _LABEL3[rank]
    else:
        label = "trend_down" if rank == 0 else ("trend_up" if rank == n_states - 1 else "range")
    tail = path[-12:]
    return {
        "regime": label, "state": cur, "rank": rank, "n_states": n_states, "multivariate": True,
        "confidence": round(model["post_last"][cur], 3),
        "persistence": round(sum(1 for s in tail if s == cur) / len(tail), 3),
        "state_mean": round(model["means"][cur][0], 4),
        "state_vol": round(model["means"][cur][1], 4) if model["dims"] > 1 else None,
        "means": [round(model["means"][i][0], 4) for i in range(n_states)],
        "vols": [round(model["means"][i][1], 4) for i in range(n_states)] if model["dims"] > 1 else None,
        "loglik": round(model["loglik"], 2),
        "model": {"n_states": n_states, "dims": model["dims"], "start": model["start"],
                  "trans": model["trans"], "means": model["means"], "vars": model["vars"]},
        **_anticipate(model, cur, order, n_states),
    }


_LABEL3 = ["trend_down", "range", "trend_up"]


def _label_for(rank: int, n_states: int) -> str:
    if n_states == 3:
        return _LABEL3[rank]
    return "trend_down" if rank == 0 else ("trend_up" if rank == n_states - 1 else "range")


def _anticipate(model: dict, cur: int, order: list[int], n_states: int) -> dict:
    """Antizipiert das NÄCHSTE Regime aus der HMM-Übergangszeile des aktuellen Zustands."""
    trow = model["trans"][cur]
    dist: dict[str, float] = {}
    for s in range(n_states):
        lbl = _label_for(order.index(s), n_states)
        dist[lbl] = round(dist.get(lbl, 0.0) + trow[s], 3)
    nr = max(dist, key=dist.get)
    return {"next_regime": nr, "next_regime_prob": dist[nr], "stay_prob": round(trow[cur], 3),
            "transition_dist": dist}


def classify(obs: list[float], n_states: int = 3) -> dict | None:
    """Fit + Viterbi-Decode; mappt den AKTUELLEN Zustand nach Mittelwert-Rang auf das Regime-Label.

    Returns u.a. ``regime`` (trend_down/range/trend_up), ``confidence`` (geglättete Posterior-
    Wahrscheinlichkeit des aktuellen Zustands), ``persistence`` (Anteil der letzten 12 Schritte im
    selben Zustand) und die gefitteten Zustands-Mittel/-Varianzen. None bei zu wenig Daten.
    """
    model = fit(obs, n_states=n_states)
    if not model:
        return None
    path = viterbi(obs, model)
    cur = path[-1]
    order = sorted(range(n_states), key=lambda i: model["means"][i])   # aufsteigend nach Mittelwert
    rank = order.index(cur)
    if n_states == 3:
        label = _LABEL3[rank]
    else:
        label = "trend_down" if rank == 0 else ("trend_up" if rank == n_states - 1 else "range")
    tail = path[-12:]
    persistence = round(sum(1 for s in tail if s == cur) / len(tail), 3)
    return {
        "regime": label, "state": cur, "rank": rank, "n_states": n_states,
        "confidence": round(model["post_last"][cur], 3), "persistence": persistence,
        "state_mean": round(model["means"][cur], 4), "state_std": round(model["vars"][cur] ** 0.5, 4),
        "means": [round(m, 4) for m in model["means"]],
        "stds": [round(v ** 0.5, 4) for v in model["vars"]],
        "loglik": round(model["loglik"], 2),
        **_anticipate(model, cur, order, n_states),
    }
