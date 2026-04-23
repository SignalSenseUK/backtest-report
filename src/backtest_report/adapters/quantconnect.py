"""QuantConnect adapter — fetch cloud backtest results and convert to BacktestData.

This module provides functions to extract backtest data and configuration
from QuantConnect cloud backtests via the QC API v2.

Usage:
    from backtest_report.adapters.quantconnect import fetch_backtest_data

    data, config = fetch_backtest_data(
        project_id=30522360,
        backtest_id="283c46d6a20c169a7a75e3a9a371a68d",
    )

    # Then write to experiment directory:
    from backtest_report.persist import write_experiment_dir
    write_experiment_dir(Path("/store/backtests/my_experiment"), data, config, {})
"""
from __future__ import annotations

import logging
from base64 import b64encode
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from time import time
from typing import Any

import pandas as pd
import requests  # type: ignore[import-untyped]

logger = logging.getLogger("backtest_report")

QC_BASE_URL = "https://www.quantconnect.com/api/v2"


# ── Exceptions ───────────────────────────────────────────────────────


class QuantConnectAuthError(Exception):
    """Raised when QC API authentication fails."""
    pass


class QuantConnectAPIError(Exception):
    """Raised when a QC API request fails."""
    pass


class QuantConnectNotFoundError(Exception):
    """Raised when a backtest or project is not found."""
    pass


# ── API layer ────────────────────────────────────────────────────────


def _get_headers(user_id: str, api_token: str) -> dict[str, str]:
    """Generate authenticated headers for QC API v2.

    QC API v2 uses a timestamped SHA-256 hash of the API token,
    NOT plain Basic auth.
    """
    timestamp = f"{int(time())}"
    time_stamped_token = f"{api_token}:{timestamp}".encode()
    hashed_token = sha256(time_stamped_token).hexdigest()
    auth_bytes = f"{user_id}:{hashed_token}".encode()
    auth_str = b64encode(auth_bytes).decode("ascii")
    return {
        "Authorization": f"Basic {auth_str}",
        "Timestamp": timestamp,
    }


def _api_post(
    endpoint: str,
    user_id: str,
    api_token: str,
    data: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    """Make an authenticated POST request to QC API v2."""
    url = f"{QC_BASE_URL}/{endpoint}"
    resp = requests.post(
        url,
        headers=_get_headers(user_id, api_token),
        json=data or {},
        timeout=timeout,
    )
    resp.raise_for_status()
    return dict(resp.json())


def authenticate(user_id: str, api_token: str) -> bool:
    """Verify QC API credentials."""
    resp = _api_post("authenticate", user_id, api_token)
    if not resp.get("success"):
        raise QuantConnectAuthError(f"QC API authentication failed: {resp}")
    return True


def list_backtests(
    user_id: str,
    api_token: str,
    project_id: int,
) -> list[dict[str, Any]]:
    """List backtests for a project."""
    resp = _api_post("backtests/read", user_id, api_token, {
        "projectId": project_id,
    })
    if not resp.get("success"):
        raise QuantConnectAPIError(f"Failed to list backtests: {resp.get('errors')}")
    return list(resp.get("backtests", []))


def get_backtest_info(
    user_id: str,
    api_token: str,
    project_id: int,
    backtest_id: str,
) -> dict[str, Any]:
    """Fetch backtest metadata, statistics, and totalPerformance."""
    resp = _api_post("backtests/read", user_id, api_token, {
        "projectId": project_id,
        "backtestId": backtest_id,
    })
    if not resp.get("success"):
        errors = resp.get("errors", [])
        raise QuantConnectAPIError(f"Failed to read backtest: {errors}")

    bt = resp.get("backtest", {})
    if not bt:
        raise QuantConnectNotFoundError(
            f"Backtest {backtest_id} not found in project {project_id}"
        )
    return dict(bt)


def get_chart(
    user_id: str,
    api_token: str,
    project_id: int,
    backtest_id: str,
    chart_name: str,
    start: int | None = None,
    end: int | None = None,
    count: int = 50000,
) -> dict[str, Any]:
    """Fetch chart data from a backtest via /backtests/chart/read.

    Common chart names: "Strategy Equity", "Benchmark", "Drawdown",
    "Portfolio Margin", "Assets Sales Volume", "Exposure", "Capacity".
    """
    payload: dict[str, Any] = {
        "projectId": project_id,
        "backtestId": backtest_id,
        "name": chart_name,
        "count": count,
    }
    if start is not None:
        payload["start"] = start
    if end is not None:
        payload["end"] = end

    resp = _api_post("backtests/chart/read", user_id, api_token, payload)
    if not resp.get("success"):
        raise QuantConnectAPIError(
            f"Failed to read chart '{chart_name}': {resp.get('errors')}"
        )
    return dict(resp["chart"])


def _safe_get_chart(
    user_id: str,
    api_token: str,
    project_id: int,
    backtest_id: str,
    chart_name: str,
    count: int = 50000,
) -> dict[str, Any] | None:
    """Fetch a chart, returning None on failure instead of raising."""
    try:
        return get_chart(user_id, api_token, project_id, backtest_id, chart_name, count=count)
    except Exception as e:
        logger.warning("Could not fetch chart '%s': %s", chart_name, e)
        return None


# ── Parsing helpers ──────────────────────────────────────────────────


def _parse_ts_value_pairs(values: list) -> dict[pd.Timestamp, float]:
    """Parse [timestamp_seconds, value] pairs into {Timestamp: float}."""
    result: dict[pd.Timestamp, float] = {}
    for v in values:
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            ts = pd.Timestamp(v[0], unit="s", tz="UTC")
            result[ts.normalize()] = v[1]
        elif isinstance(v, dict):
            ts = pd.Timestamp(v.get("x", v.get("time", 0)), unit="s", tz="UTC")
            y_val = v.get("y", v.get("value", 0))
            result[ts.normalize()] = float(y_val) if y_val is not None else 0.0
    return result


def _parse_ts_ohlc_pairs(values: list) -> dict[pd.Timestamp, float]:
    """Parse [timestamp_seconds, o, h, l, close] pairs, extracting close."""
    result: dict[pd.Timestamp, float] = {}
    for v in values:
        if isinstance(v, (list, tuple)) and len(v) >= 5:
            ts = pd.Timestamp(v[0], unit="s", tz="UTC")
            result[ts.normalize()] = v[4]  # close
        elif isinstance(v, (list, tuple)) and len(v) >= 2:
            ts = pd.Timestamp(v[0], unit="s", tz="UTC")
            result[ts.normalize()] = v[1]
        elif isinstance(v, dict):
            ts = pd.Timestamp(v.get("x", v.get("time", 0)), unit="s", tz="UTC")
            y_val = v.get("y", v.get("close", v.get("value", 0)))
            result[ts.normalize()] = float(y_val) if y_val is not None else 0.0
    return result


def parse_equity_chart(chart: dict[str, Any]) -> pd.Series:
    """Parse Strategy Equity chart into a daily equity Series.

    QC returns equity as [timestamp_seconds, open, high, low, close].
    We extract the daily close.
    """
    series = chart.get("series", {})
    equity_data = series.get("Equity", series.get("equity", {}))
    values = equity_data.get("values", [])

    if not values:
        raise ValueError("No equity values found in Strategy Equity chart")

    daily_close = _parse_ts_ohlc_pairs(values)

    if not daily_close:
        raise ValueError("No parseable equity values found")

    equity = pd.Series(daily_close).sort_index()
    equity.index = pd.DatetimeIndex(equity.index, name="date")
    equity.name = "equity"
    return equity


def parse_returns_series(chart: dict[str, Any]) -> pd.Series | None:
    """Parse daily return series from chart if available.

    QC provides a "Return" series with [timestamp_seconds, return_pct].
    Values are in percentage form (e.g. 2.5 = 2.5%), normalised to decimal.
    """
    series = chart.get("series", {})
    for key in ("Return", "Daily Return", "return"):
        if key in series:
            values = series[key].get("values", [])
            if not values:
                continue

            returns: dict[pd.Timestamp, float] = {}
            for v in values:
                if isinstance(v, (list, tuple)) and len(v) >= 2:
                    ts = pd.Timestamp(v[0], unit="s", tz="UTC")
                    ret = float(v[1])
                    if abs(ret) > 1:
                        ret = ret / 100
                    returns[ts.normalize()] = ret
                elif isinstance(v, dict):
                    ts = pd.Timestamp(v.get("x", 0), unit="s", tz="UTC")
                    ret_val = v.get("y", v.get("value", 0))
                    ret = float(ret_val) if ret_val is not None else 0.0
                    if abs(ret) > 1:
                        ret = ret / 100
                    returns[ts.normalize()] = ret

            if returns:
                s = pd.Series(returns).sort_index()
                s.index = pd.DatetimeIndex(s.index, name="date")
                s.name = "returns"
                return s
    return None


def parse_benchmark_chart(chart: dict[str, Any]) -> pd.Series | None:
    """Parse Benchmark chart into a daily benchmark returns Series."""
    series = chart.get("series", {})
    for _skey, sdata in series.items():
        values = sdata.get("values", [])
        if not values:
            continue

        daily_vals = _parse_ts_ohlc_pairs(values)
        if not daily_vals:
            # Try simple value pairs
            daily_vals = _parse_ts_value_pairs(values)

        if daily_vals:
            benchmark = pd.Series(daily_vals).sort_index()
            benchmark.index = pd.DatetimeIndex(benchmark.index, name="date")
            returns = benchmark.pct_change().dropna()
            returns.name = "benchmark_returns"
            return returns
    return None


def parse_per_instrument_chart(
    chart: dict[str, Any],
) -> dict[str, pd.Series]:
    """Parse a chart with per-instrument series (e.g. Portfolio Margin, Assets Sales Volume).

    QC charts like "Portfolio Margin" have series keyed by symbol:
      {"series": {"SPY": {"values": [[ts, val], ...]}, "QQQ": {...}}}

    Returns:
        dict mapping symbol → pd.Series with DatetimeIndex
    """
    result: dict[str, pd.Series] = {}
    series = chart.get("series", {})
    for symbol, sdata in series.items():
        values = sdata.get("values", [])
        if not values:
            continue
        daily_vals = _parse_ts_value_pairs(values)
        if daily_vals:
            s = pd.Series(daily_vals).sort_index()
            s.index = pd.DatetimeIndex(s.index, name="date")
            s.name = symbol
            result[symbol] = s
    return result


def parse_exposure_chart(chart: dict[str, Any]) -> pd.DataFrame:
    """Parse Exposure chart into a DataFrame of long/short ratios.

    QC returns series like "Equity - Long Ratio", "Equity - Short Ratio"
    with [timestamp_seconds, ratio] pairs.

    Returns:
        DataFrame with DatetimeIndex and columns for each exposure type
    """
    series = chart.get("series", {})
    frames: dict[str, pd.Series] = {}
    for skey, sdata in series.items():
        values = sdata.get("values", [])
        if not values:
            continue
        daily_vals = _parse_ts_value_pairs(values)
        if daily_vals:
            s = pd.Series(daily_vals).sort_index()
            s.index = pd.DatetimeIndex(s.index, name="date")
            frames[skey] = s

    if not frames:
        return pd.DataFrame()

    df = pd.DataFrame(frames)
    df.index = pd.DatetimeIndex(df.index, name="date")
    return df


def parse_closed_trades(
    closed_trades: list[dict[str, Any]],
) -> pd.DataFrame:
    """Parse closedTrades from totalPerformance into a DataFrame.

    Each trade has: symbol, entryTime, exitTime, entryPrice, exitPrice,
    direction, quantity, totalFees, profitLoss, mae, mfe, duration.

    Returns:
        DataFrame with one row per closed trade
    """
    if not closed_trades:
        return pd.DataFrame()

    rows = []
    for t in closed_trades:
        sym = t.get("symbol", {})
        rows.append({
            "symbol": sym.get("value", sym.get("Symbol", "UNKNOWN")),
            "entry_time": pd.Timestamp(t.get("entryTime", 0)),
            "exit_time": pd.Timestamp(t.get("exitTime", 0)),
            "direction": t.get("direction", ""),
            "quantity": float(t.get("quantity", 0)),
            "entry_price": float(t.get("entryPrice", 0)),
            "exit_price": float(t.get("exitPrice", 0)),
            "profit_loss": float(t.get("profitLoss", 0)),
            "total_fees": float(t.get("totalFees", 0)),
            "mae": float(t.get("mae", 0)),
            "mfe": float(t.get("mfe", 0)),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["exit_date"] = pd.to_datetime(df["exit_time"]).dt.normalize()
    return df


# ── Per-instrument PnL and position builders ─────────────────────────


def build_instrument_pnl_from_margin(
    portfolio_returns: pd.Series,
    margin_chart: dict[str, Any],
) -> tuple[pd.DataFrame, list[str]]:
    """Build per-instrument PnL from Portfolio Margin chart data.

    Uses per-symbol daily margin as a weight proxy to decompose portfolio
    returns into instrument-level PnL.

    Strategy:
        - Get daily margin per symbol from the chart
        - Compute each symbol's weight as margin / total_margin
        - instrument_pnl[t, sym] = portfolio_return[t] * weight[t, sym]

    Args:
        portfolio_returns: daily portfolio return series
        margin_chart: parsed Portfolio Margin chart dict from QC API

    Returns:
        tuple of (instrument_pnl DataFrame, list of instruments)
    """
    per_instr = parse_per_instrument_chart(margin_chart)
    if not per_instr:
        return pd.DataFrame(), []

    instruments = sorted(per_instr.keys())

    # Align all series to the same dates
    margin_df = pd.DataFrame(per_instr)
    margin_df = margin_df.reindex(portfolio_returns.index)

    # Forward-fill margin values (QC only reports on days with changes)
    margin_df = margin_df.ffill().fillna(0)

    # Compute weights: each symbol's margin / total margin
    total_margin = margin_df.sum(axis=1).replace(0, 1)  # avoid div by zero
    weights = margin_df.div(total_margin, axis=0)

    # Decompose portfolio returns by weight
    pnl_data = {}
    for instr in instruments:
        pnl_data[instr] = portfolio_returns * weights[instr]

    instrument_pnl = pd.DataFrame(pnl_data, index=portfolio_returns.index)
    instrument_pnl.index = pd.DatetimeIndex(instrument_pnl.index, name="date")

    logger.info(
        "Built per-instrument PnL from margin chart: %d instruments, %d days",
        len(instruments),
        len(instrument_pnl),
    )
    return instrument_pnl, instruments


def build_positions_from_margin(
    portfolio_returns: pd.Series,
    margin_chart: dict[str, Any],
) -> pd.DataFrame:
    """Build per-instrument position weights from Portfolio Margin chart.

    Returns a DataFrame of weight allocations (0-1) per instrument per day,
    where each row sums to ~1.0 when fully invested.

    Args:
        portfolio_returns: daily portfolio return series (for date alignment)
        margin_chart: parsed Portfolio Margin chart dict from QC API

    Returns:
        DataFrame with DatetimeIndex, columns = instruments, values = weights
    """
    per_instr = parse_per_instrument_chart(margin_chart)
    if not per_instr:
        return pd.DataFrame()

    instruments = sorted(per_instr.keys())

    margin_df = pd.DataFrame(per_instr)
    margin_df = margin_df.reindex(portfolio_returns.index)
    margin_df = margin_df.ffill().fillna(0)

    total_margin = margin_df.sum(axis=1).replace(0, 1)
    weights = margin_df.div(total_margin, axis=0)

    positions = pd.DataFrame(
        {instr: weights[instr].values for instr in instruments},
        index=portfolio_returns.index,
    )
    positions.index = pd.DatetimeIndex(positions.index, name="date")

    logger.info(
        "Built per-instrument positions from margin chart: %d instruments",
        len(instruments),
    )
    return positions


def build_instrument_pnl_from_trades(
    closed_trades_df: pd.DataFrame,
    portfolio_returns: pd.Series,
    instruments: list[str],
) -> pd.DataFrame:
    """Build daily per-instrument PnL from closed trades.

    Aggregates trade PnL by exit date and symbol, then reindexes to match
    the portfolio returns dates (filling non-trade days with 0).

    Args:
        closed_trades_df: DataFrame from parse_closed_trades()
        portfolio_returns: daily portfolio return series
        instruments: list of instrument symbols

    Returns:
        DataFrame with DatetimeIndex, columns = instruments, values = daily PnL
    """
    if closed_trades_df.empty:
        return pd.DataFrame(0, index=portfolio_returns.index, columns=instruments)

    # Aggregate by (exit_date, symbol)
    pnl_by_date = (
        closed_trades_df
        .groupby(["exit_date", "symbol"])["profit_loss"]
        .sum()
        .unstack(fill_value=0)
    )
    pnl_by_date.index = pd.DatetimeIndex(pnl_by_date.index, name="date")

    # Ensure all instruments present
    for instr in instruments:
        if instr not in pnl_by_date.columns:
            pnl_by_date[instr] = 0.0

    # Reindex to match portfolio returns dates
    pnl_by_date = pnl_by_date.reindex(portfolio_returns.index, fill_value=0)
    pnl_by_date = pnl_by_date[instruments]  # consistent column order

    return pnl_by_date


def build_positions_from_trades(
    closed_trades_df: pd.DataFrame,
    portfolio_returns: pd.Series,
    instruments: list[str],
) -> pd.DataFrame:
    """Build approximate position weights from closed trades.

    Uses a simple heuristic: if a symbol has an open trade on a given day,
    assign equal weight across all symbols with open trades.

    For more accurate positions, use margin chart data instead.

    Args:
        closed_trades_df: DataFrame from parse_closed_trades()
        portfolio_returns: daily portfolio return series
        instruments: list of instrument symbols

    Returns:
        DataFrame with DatetimeIndex, columns = instruments, values = weights
    """
    dates = portfolio_returns.index
    positions = pd.DataFrame(0.0, index=dates, columns=instruments)
    positions.index = pd.DatetimeIndex(positions.index, name="date")

    if closed_trades_df.empty:
        # No trades — assume equal weight always invested
        n = len(instruments) or 1
        for instr in instruments:
            positions[instr] = 1.0 / n
        return positions

    # Mark days where each symbol has an open position
    for _, trade in closed_trades_df.iterrows():
        entry = pd.Timestamp(trade["entry_time"]).normalize()
        exit_d = pd.Timestamp(trade["exit_time"]).normalize()
        sym = trade["symbol"]
        if sym not in instruments:
            continue
        mask = (dates >= entry) & (dates <= exit_d)
        positions.loc[mask, sym] = 1.0

    # Normalise rows to sum to 1
    row_sums = positions.sum(axis=1).replace(0, 1)
    positions = positions.div(row_sums, axis=0)

    return positions


# ── Main entry points ────────────────────────────────────────────────


def fetch_backtest(
    project_id: int,
    backtest_id: str,
    user_id: str | None = None,
    api_token: str | None = None,
    strategy_name: str | None = None,
    risk_target_annual_pct: float = 20.0,
) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Fetch a QC cloud backtest and extract all data.

    Returns:
        tuple of:
            - portfolio_returns (Series)
            - instrument_pnl (DataFrame)
            - positions (DataFrame)
            - instrument_meta (dict[str, dict])
            - config_dict (dict for BacktestConfig)
    """
    from os import environ

    uid = user_id or environ.get("QC_USER_ID", "")
    token = api_token or environ.get("QC_API_TOKEN", "")

    if not uid or not token:
        raise ValueError(
            "QC credentials required. Pass user_id/api_token or set "
            "QC_USER_ID and QC_API_TOKEN environment variables."
        )

    # 1. Authenticate
    authenticate(uid, token)
    logger.info("QC API authenticated for user %s", uid)

    # 2. Fetch backtest metadata with totalPerformance
    bt_info = get_backtest_info(uid, token, project_id, backtest_id)
    stats = bt_info.get("statistics", {})
    tp = bt_info.get("totalPerformance", {})
    closed_trades_raw = tp.get("closedTrades", [])
    bt_name = bt_info.get("name", "unknown")
    name = strategy_name or bt_name

    logger.info(
        "Backtest: %s (%s to %s), %d closed trades",
        bt_name,
        bt_info.get("backtestStart"),
        bt_info.get("backtestEnd"),
        len(closed_trades_raw),
    )

    # 3. Fetch equity chart
    equity_chart = get_chart(uid, token, project_id, backtest_id, "Strategy Equity")
    equity = parse_equity_chart(equity_chart)
    logger.info("Equity curve: %d days", len(equity))

    # Try to use the daily return series if available
    returns = parse_returns_series(equity_chart)
    if returns is not None and len(returns) > 1:
        portfolio_returns = returns
    else:
        portfolio_returns = equity.pct_change().dropna()
        portfolio_returns.name = "returns"
        portfolio_returns.index.name = "date"

    # 4. Fetch per-instrument data from charts
    margin_chart = _safe_get_chart(uid, token, project_id, backtest_id, "Portfolio Margin")
    _safe_get_chart(uid, token, project_id, backtest_id, "Exposure")

    # 5. Parse closed trades
    closed_trades_df = parse_closed_trades(closed_trades_raw)
    if not closed_trades_df.empty:
        logger.info(
            "Closed trades: %d trades across %d symbols",
            len(closed_trades_df),
            closed_trades_df["symbol"].nunique(),
        )

    # 6. Determine instruments (prefer margin chart → closed trades → stats)
    instruments: list[str] = []

    if margin_chart:
        per_instr = parse_per_instrument_chart(margin_chart)
        if per_instr:
            instruments = sorted(per_instr.keys())

    if not instruments and not closed_trades_df.empty:
        instruments = sorted(closed_trades_df["symbol"].unique().tolist())

    if not instruments:
        instruments = _infer_instruments(bt_info, stats)

    logger.info("Instruments: %s", instruments)

    # 7. Build per-instrument PnL
    instrument_pnl = pd.DataFrame()

    if margin_chart and len(instruments) > 1:
        # Multi-instrument: decompose using margin weights
        instrument_pnl, margin_instruments = build_instrument_pnl_from_margin(
            portfolio_returns, margin_chart
        )
        if margin_instruments:
            instruments = margin_instruments
    elif not closed_trades_df.empty:
        # Use trade-level PnL aggregated by day
        instrument_pnl = build_instrument_pnl_from_trades(
            closed_trades_df, portfolio_returns, instruments
        )

    if instrument_pnl.empty:
        # Fallback: equal-weight allocation
        n = len(instruments)
        pnl_data = dict.fromkeys(instruments, portfolio_returns.values / n)
        instrument_pnl = pd.DataFrame(pnl_data, index=portfolio_returns.index)
        instrument_pnl.index = pd.DatetimeIndex(instrument_pnl.index, name="date")

    # 8. Build positions
    positions = pd.DataFrame()

    if margin_chart and len(instruments) > 1:
        positions = build_positions_from_margin(portfolio_returns, margin_chart)
    elif not closed_trades_df.empty:
        positions = build_positions_from_trades(
            closed_trades_df, portfolio_returns, instruments
        )

    if positions.empty:
        n = len(instruments) or 1
        pos_data = {instr: [1.0 / n] * len(portfolio_returns) for instr in instruments}
        positions = pd.DataFrame(pos_data, index=portfolio_returns.index)
        positions.index = pd.DatetimeIndex(positions.index, name="date")

    # 9. Instrument metadata
    instrument_meta: dict[str, dict[str, Any]] = {
        instr: {"code": instr, "asset_class": _guess_asset_class(instr)}
        for instr in instruments
    }

    # Enrich with closed trade statistics per instrument
    if not closed_trades_df.empty:
        for instr in instruments:
            instr_trades = closed_trades_df[closed_trades_df["symbol"] == instr]
            meta = instrument_meta[instr]
            meta["total_trades"] = len(instr_trades)
            meta["total_pnl"] = float(instr_trades["profit_loss"].sum())
            meta["win_rate"] = float(
                (instr_trades["profit_loss"] > 0).mean()
            ) if len(instr_trades) > 0 else 0.0
            meta["avg_trade_pnl"] = float(
                instr_trades["profit_loss"].mean()
            ) if len(instr_trades) > 0 else 0.0
            meta["max_mae"] = float(instr_trades["mae"].min()) if len(instr_trades) > 0 else 0.0
            meta["max_mfe"] = float(instr_trades["mfe"].max()) if len(instr_trades) > 0 else 0.0

    # 10. Config
    start_equity = _parse_float(
        stats.get("Start Equity", stats.get("Starting Equity", "100000"))
    )
    start_date = portfolio_returns.index[0].date()
    end_date = portfolio_returns.index[-1].date()

    # Build per-instrument trade stats for config_overrides
    instr_trade_stats = {}
    if not closed_trades_df.empty:
        for instr in instruments:
            instr_trades = closed_trades_df[closed_trades_df["symbol"] == instr]
            if len(instr_trades) > 0:
                instr_trade_stats[instr] = {
                    "trades": len(instr_trades),
                    "total_pnl": round(float(instr_trades["profit_loss"].sum()), 2),
                    "win_rate": round(float((instr_trades["profit_loss"] > 0).mean()), 4),
                    "avg_pnl": round(float(instr_trades["profit_loss"].mean()), 2),
                }

    config_dict = {
        "experiment_id": f"qc-{name.lower().replace(' ', '-')}",
        "strategy_name": name,
        "engine": "quantconnect-lean",
        "instrument_universe": instruments,
        "start_date": start_date,
        "end_date": end_date,
        "capital": start_equity,
        "risk_target_annual_pct": risk_target_annual_pct,
        "data_sources": ["quantconnect-cloud"],
        "config_overrides": {
            "project_id": project_id,
            "backtest_id": backtest_id,
            "closed_trades_count": len(closed_trades_raw),
            "qc_statistics": {
                k: stats[k]
                for k in [
                    "Net Profit", "Sharpe Ratio", "Sortino Ratio", "Drawdown",
                    "Compounding Annual Return", "Total Orders", "Win Rate",
                    "Alpha", "Beta", "Annual Standard Deviation",
                    "Total Fees", "Probabilistic Sharpe Ratio",
                ]
                if k in stats
            },
            "instrument_trade_stats": instr_trade_stats,
        },
    }

    return portfolio_returns, instrument_pnl, positions, instrument_meta, config_dict


def fetch_backtest_data(
    project_id: int,
    backtest_id: str,
    user_id: str | None = None,
    api_token: str | None = None,
    strategy_name: str | None = None,
    risk_target_annual_pct: float = 20.0,
) -> tuple[Any, Any]:
    """Fetch a QC cloud backtest and return BacktestData + BacktestConfig.

    This is the high-level entry point that returns validated model objects,
    ready for write_experiment_dir() or BacktestReport.generate().

    Returns:
        tuple of (BacktestData, BacktestConfig)
    """
    from backtest_report.models import BacktestConfig, BacktestData, InstrumentMeta

    (
        portfolio_returns,
        instrument_pnl,
        positions,
        instrument_meta_raw,
        config_dict,
    ) = fetch_backtest(
        project_id=project_id,
        backtest_id=backtest_id,
        user_id=user_id,
        api_token=api_token,
        strategy_name=strategy_name,
        risk_target_annual_pct=risk_target_annual_pct,
    )

    config = BacktestConfig.model_validate(config_dict)

    instrument_meta = {
        code: InstrumentMeta.model_validate(meta)
        for code, meta in instrument_meta_raw.items()
    }

    # Try to fetch benchmark
    uid = user_id or __import__("os").environ.get("QC_USER_ID", "")
    token = api_token or __import__("os").environ.get("QC_API_TOKEN", "")
    benchmark_returns = None
    try:
        bench_chart = get_chart(uid, token, project_id, backtest_id, "Benchmark")
        benchmark_returns = parse_benchmark_chart(bench_chart)
        if benchmark_returns is not None:
            logger.info("Benchmark: %d days", len(benchmark_returns))
    except Exception as e:
        logger.warning("Could not fetch benchmark: %s", e)

    data = BacktestData(
        portfolio_returns=portfolio_returns,
        instrument_pnl=instrument_pnl,
        positions=positions,
        instrument_meta=instrument_meta,
        benchmark_returns=benchmark_returns,
    )

    return data, config


# ── CLI convenience ──────────────────────────────────────────────────


def fetch_and_write(
    project_id: int,
    backtest_id: str,
    output_dir: Path,
    user_id: str | None = None,
    api_token: str | None = None,
    strategy_name: str | None = None,
) -> Path:
    """Fetch a QC backtest and write to an experiment directory.

    Combines fetch_backtest_data() + write_experiment_dir() + checksums.

    Returns:
        Path to the created experiment directory
    """
    from backtest_report.persist import compute_checksum, write_experiment_dir

    data, config = fetch_backtest_data(
        project_id=project_id,
        backtest_id=backtest_id,
        user_id=user_id,
        api_token=api_token,
        strategy_name=strategy_name,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = config.strategy_name.lower().replace(" ", "-")
    experiment_id = f"{slug}_{timestamp}"
    exp_dir = Path(output_dir) / experiment_id

    write_experiment_dir(exp_dir, data, config, data_checksums={})

    checksums = {}
    for fname in ["portfolio_returns.parquet", "instrument_pnl.parquet", "positions.parquet"]:
        fpath = exp_dir / fname
        if fpath.exists():
            checksums[fname] = compute_checksum(fpath)

    write_experiment_dir(exp_dir, data, config, data_checksums=checksums)
    logger.info("Experiment written to: %s", exp_dir)

    return exp_dir


# ── Helpers ──────────────────────────────────────────────────────────


def _guess_asset_class(symbol: str) -> str:
    """Guess asset class from a QC symbol or security type hint."""
    s = symbol.upper()
    if s in ("SPY", "QQQ", "IWM", "AAPL", "MSFT", "GOOG"):
        return "equity"
    for prefix in ("ES", "NQ", "CL", "GC", "ZB", "ZN", "ZF", "ZW", "ZC", "ZS"):
        if s.startswith(prefix):
            return "future"
    for pair in ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD"):
        if s.startswith(pair[:3]):
            return "fx"
    return "equity"


def _infer_instruments(bt_info: dict, stats: dict) -> list[str]:
    """Infer traded instruments from backtest metadata."""
    lowest = stats.get("Lowest Capacity Asset", "")
    if isinstance(lowest, str) and lowest.strip():
        parts = lowest.strip().split()
        if parts:
            return [parts[0]]

    orders = bt_info.get("orders", [])
    if orders:
        symbols = set()
        for order in orders:
            sym = order.get("symbol", {}).get("value", "")
            if sym:
                symbols.add(sym)
        if symbols:
            return sorted(symbols)

    return ["UNKNOWN"]


def _parse_float(value: str | float) -> float:
    """Parse a string value to float, stripping currency symbols and commas."""
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).replace(",", "").replace("$", "").strip())
