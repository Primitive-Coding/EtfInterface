import pandas as pd
import subprocess
from holdings_download import HoldingsDownloader


class ETF:
    def __init__(self, local_path: str = "M:\\Finance\\etfs") -> None:
        self.local_path = local_path

    def get_tickers(self, ticker: str):
        path = f"{self.local_path}\\{ticker.upper()}.csv"
        df = pd.read_csv(path)
        tickers = df["Symbol"].to_list()
        tickers = [ticker for ticker in tickers if ticker != "--"]
        return tickers

    def download_tickers(self, ticker):
        export_dir = "M:\\Finance\\etfs"
        command = ["python", "holdings_downloader.py", "--symbol", ticker.upper()]
        result = subprocess.run(command, capture_output=True, text=True)
        # downloader = HoldingsDownloader(export_dir)
        # downloader.run_schwab_download()


if __name__ == "__main__":

    etf = ETF()

    tickers = etf.download_tickers("SCHG")
    print(f"Tickers: {tickers}")
