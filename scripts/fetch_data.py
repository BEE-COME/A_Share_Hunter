#!/usr/bin/env python3
"""
A股数据抓取脚本
使用 AkShare 获取个股收盘价、换手率、均线数据
"""

import json
import os
from pathlib import Path
from datetime import datetime

import akshare as ak
import pandas as pd


def get_project_root() -> Path:
    return Path(__file__).parent.parent


def load_config() -> dict:
    config_path = get_project_root() / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_stock_data(stock_code: str) -> pd.DataFrame:
    """
    使用 AkShare 获取A股历史日线数据
    返回包含日期、收盘价、换手率、MA5 的 DataFrame
    """
    try:
        # 使用东方财富数据源
        df = ak.stock_zh_a_hist(
            symbol=stock_code,
            period="daily",
            start_date="20240101",
            end_date=datetime.now().strftime("%Y%m%d"),
            adjust="qfq"
        )

        # 重命名列
        df = df.rename(columns={
            "日期": "date",
            "收盘": "close",
            "换手率": "turnover_rate"
        })

        # 选取需要的列
        df = df[["date", "close", "turnover_rate"]].copy()

        # 计算5日均线
        df["ma5"] = df["close"].rolling(window=5).mean().round(2)

        return df

    except Exception as e:
        print(f"[ERROR] 获取股票 {stock_code} 数据失败: {e}")
        return pd.DataFrame()


def save_to_csv(df: pd.DataFrame, stock_code: str) -> None:
    data_dir = get_project_root() / "data"
    data_dir.mkdir(exist_ok=True)

    csv_path = data_dir / f"{stock_code}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"[OK] 已保存: {csv_path} ({len(df)} 条记录)")


def main():
    config = load_config()
    portfolio = config.get("portfolio", [])

    if not portfolio:
        print("[WARN] config.json 中未配置 portfolio")
        return

    print(f"[INFO] 开始抓取 {len(portfolio)} 只股票数据...")

    for stock_code in portfolio:
        print(f"\n--- {stock_code} ---")
        df = fetch_stock_data(stock_code)
        if not df.empty:
            save_to_csv(df, stock_code)
            # 打印最新数据
            latest = df.iloc[-1]
            print(f"  最新日期: {latest['date']}")
            print(f"  收盘价: {latest['close']}")
            print(f"  换手率: {latest['turnover_rate']}%")
            print(f"  MA5: {latest['ma5']}")


if __name__ == "__main__":
    main()
