#!/usr/bin/env python3
"""
A股盘中监控报警脚本
轮询价格并在触发条件时发送钉钉/微信 Webhook 报警
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import akshare as ak
import pandas as pd
import requests


def get_project_root() -> Path:
    return Path(__file__).parent.parent


def setup_logging():
    log_dir = get_project_root() / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "monitor.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


logger = setup_logging()


def load_config() -> dict:
    config_path = get_project_root() / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_stock_data(stock_code: str) -> pd.DataFrame:
    csv_path = get_project_root() / "data" / f"{stock_code}.csv"
    if not csv_path.exists():
        logger.warning(f"数据文件不存在: {csv_path}")
        return pd.DataFrame()

    df = pd.read_csv(csv_path)
    return df


def get_realtime_price(stock_code: str) -> float | None:
    """
    获取A股实时价格
    """
    try:
        # 使用 AkShare 的实时行情接口
        df = ak.stock_zh_a_spot_em()

        # 根据代码匹配
        stock_info = df[df["代码"] == stock_code]

        if stock_info.empty:
            logger.error(f"未找到股票 {stock_code} 的实时数据")
            return None

        price = float(stock_info.iloc[0]["最新价"])
        return price

    except Exception as e:
        logger.error(f"获取 {stock_code} 实时价格失败: {e}")
        return None


def send_webhook_alert(message: str, config: dict) -> bool:
    """
    发送钉钉/微信 Webhook 报警
    """
    alert_config = config.get("alert", {})
    webhook_url = alert_config.get("webhook_url", "")
    webhook_type = alert_config.get("webhook_type", "dingtalk")

    if not webhook_url or "YOUR_TOKEN_HERE" in webhook_url:
        logger.warning("Webhook URL 未配置，跳过发送")
        return False

    headers = {"Content-Type": "application/json"}

    if webhook_type == "dingtalk":
        payload = {
            "msgtype": "text",
            "text": {"content": message}
        }
    else:
        # 微信格式类似
        payload = {
            "msgtype": "text",
            "text": {"content": message}
        }

    try:
        response = requests.post(webhook_url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Webhook 报警发送成功")
            return True
        else:
            logger.error(f"Webhook 发送失败: {response.status_code} {response.text}")
            return False
    except Exception as e:
        logger.error(f"Webhook 请求异常: {e}")
        return False


def check_alert_conditions(stock_code: str, current_price: float, config: dict, df: pd.DataFrame) -> list[str]:
    """
    检查报警条件
    返回触发的报警信息列表
    """
    alerts = []
    risk_config = config.get("risk_management", {})
    stop_loss_pct = risk_config.get("hard_stop_loss_pct", 8)

    # 获取最新 MA5
    if not df.empty:
        latest_ma5 = df.iloc[-1].get("ma5")
        if pd.notna(latest_ma5):
            if current_price <= latest_ma5:
                alerts.append(f"⚠️ {stock_code} 跌破5日均线\n"
                              f"当前价: {current_price:.2f}, MA5: {latest_ma5:.2f}")

    # 检查止损线（假设成本价为最新收盘价）
    if not df.empty:
        cost_price = df.iloc[-1].get("close", current_price)
        stop_loss_price = cost_price * (1 - stop_loss_pct / 100)
        if current_price <= stop_loss_price:
            alerts.append(f"🚨 {stock_code} 触及止损线\n"
                          f"当前价: {current_price:.2f}, 止损价: {stop_loss_price:.2f} "
                          f"(止损比例: {stop_loss_pct}%)")

    return alerts


def monitor_loop(config: dict):
    """
    主监控循环
    """
    portfolio = config.get("portfolio", [])
    poll_interval = config.get("alert", {}).get("poll_interval_sec", 60)

    logger.info(f"开始监控 {len(portfolio)} 只股票，轮询间隔 {poll_interval} 秒")

    while True:
        try:
            now = datetime.now()
            # 检查是否在交易时段（工作日 9:30-11:30, 13:00-15:00）
            hour = now.hour
            minute = now.minute
            weekday = now.weekday()

            is_trading_time = (
                weekday < 5 and  # 周一到周五
                ((9 <= hour < 12) or (13 <= hour < 15)) and
                not (hour == 9 and minute < 30) and
                not (hour == 11 and minute > 30)
            )

            if is_trading_time:
                logger.info("--- 开始轮询 ---")

                for stock_code in portfolio:
                    # 加载历史数据
                    df = load_stock_data(stock_code)

                    # 获取实时价格
                    current_price = get_realtime_price(stock_code)

                    if current_price is not None:
                        logger.info(f"{stock_code}: 当前价 {current_price:.2f}")

                        # 检查报警条件
                        alerts = check_alert_conditions(stock_code, current_price, config, df)

                        for alert in alerts:
                            logger.warning(alert)
                            send_webhook_alert(alert, config)
            else:
                logger.debug(f"非交易时段，等待中...")

            time.sleep(poll_interval)

        except KeyboardInterrupt:
            logger.info("用户中断，退出监控")
            break
        except Exception as e:
            logger.error(f"监控异常: {e}")
            time.sleep(poll_interval)


def main():
    logger.info("=" * 50)
    logger.info("A股监控报警系统启动")
    logger.info("=" * 50)

    config = load_config()

    # 检查是否有持仓
    if not config.get("portfolio"):
        logger.error("config.json 中未配置 portfolio")
        return

    monitor_loop(config)


if __name__ == "__main__":
    main()
