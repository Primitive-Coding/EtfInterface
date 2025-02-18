import argparse
import time

# Data
import math
import pandas as pd

# Webscraping
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait

import warnings

# Suppress future warnings
warnings.simplefilter(action="ignore", category=FutureWarning)


class HoldingsDownloader:
    def __init__(self, export_dir: str):
        self.start_time = time.time()
        self.export_dir = export_dir
        # variables
        self.firefox_options = Options()  # default: headless
        self.etf_symbols = []
        self.valid_etfs = []
        self.log_entries = []
        self.file_name = ""
        self.num_files = 0
        self.wait_time = 15
        self.log_mode = False
        self.quiet_mode = False
        self.sort_mode = False
        self.raw_mode = False
        # init
        self._parse_command_args()
        if self.file_name:
            self._read_input_file()
        if self.sort_mode:
            self.etf_symbols.sort()

    def _parse_command_args(self):
        parser = argparse.ArgumentParser(
            formatter_class=lambda prog: argparse.HelpFormatter(
                prog, max_help_position=27
            )
        )  # type error is ok

        title_group = parser.add_argument_group(
            title="required arguments"
        )  # required arguments header in output
        input_type_group = title_group.add_mutually_exclusive_group(required=True)
        input_type_group.add_argument(
            "--symbol", nargs="+", metavar="SYM", help="specify one or more ETF symbols"
        )
        input_type_group.add_argument(
            "--file",
            metavar="FILE",
            help="specify a file containing a list of ETF symbols",
        )
        parser.add_argument(
            "-r",
            "--raw",
            action="store_true",
            help="save raw data without symbols or units",
        )
        parser.add_argument(
            "-l",
            "--log",
            action="store_true",
            help="create a log of the downloaded ETFs in etf-log.csv",
        )
        parser.add_argument(
            "-a",
            "--alpha",
            action="store_true",
            help="sort ETF symbols into alphabetical order for output",
        )
        parser.add_argument(
            "-w",
            "--window",
            action="store_false",
            help="run web driver with firefox window visible",
        )
        parser.add_argument(
            "-q",
            "--quiet",
            action="store_true",
            help="suppress verbose terminal output",
        )
        parser.add_argument(
            "-t",
            "--time",
            default=15,
            type=int,
            help="set the maximum time in seconds the program will wait for web pages to load "
            "(default: 15)",
        )
        args = parser.parse_args()
        self.firefox_options.headless = args.window
        self.quiet_mode = args.quiet
        self.log_mode = args.log
        self.sort_mode = args.alpha
        self.wait_time = args.time
        self.raw_mode = args.raw
        if args.file:
            self.file_name = args.file
        if args.symbol:
            self.etf_symbols = args.symbol

    def _read_input_file(self):
        if not self.quiet_mode:
            print("Reading symbols from {} ...".format(self.file_name), end=" ")
        with open(self.file_name, "r") as input_file:
            for name in input_file:
                self.etf_symbols.append(name[:-1])  # avoid the newline at the end
        if not self.quiet_mode:
            print("complete")

    def _convert_units_to_float(self, x):  # gets raw data for dataframe .apply()
        start = 0
        if type(x) == float:
            return x
        if x[0] == "-":  # set negative portfolio weights to 0
            return 0
        if x[0] == "$":
            start = 1
        if x[-1] == "%":
            return float(x[:-1]) / 100
        if x[-1] == "K":
            return float(x[start:-1]) * 10e3
        if x[-1] == "M":
            return float(x[start:-1]) * 10e6
        if x[-1] == "B":
            return float(x[start:-1]) * 10e9
        else:
            return float(x[start:])

    def _get_etf_from_schwab(self, etf_symbol):
        if not self.quiet_mode:
            print("Opening {} database".format(etf_symbol))
        driver = webdriver.Firefox(options=self.firefox_options)
        driver.implicitly_wait(self.wait_time)
        wait = WebDriverWait(driver, 30, poll_frequency=1)
        url = (
            "https://www.schwab.wallst.com/schwab/Prospect/research/etfs/schwabETF"
            "/index.asp?type=holdings&symbol={}".format(etf_symbol)
        )
        try:
            driver.get(url)
            show_sixty_items = driver.find_element(By.XPATH, "//a[@perpage='60']")
            show_sixty_items.click()
        except ec.NoSuchElementException:
            if not self.quiet_mode:
                print(
                    "{} is not a valid ETF (not found in schwab database)\n".format(
                        etf_symbol
                    )
                )
            driver.close()
            return False
        except ec.WebDriverException:
            if not self.quiet_mode:
                print("{} not retrieved (web driver error)\n".format(etf_symbol))
            driver.close()
            return False
        page_elt = wait.until(
            ec.visibility_of_element_located((By.CLASS_NAME, "paginationContainer"))
        )  # REQUIRED!!!
        try:
            num_pages = math.ceil(float(page_elt.text.split(" ")[4]) / 60)
        except ec.StaleElementReferenceException:  # fixes stale reference bug
            page_elt = wait.until(
                ec.visibility_of_element_located((By.CLASS_NAME, "paginationContainer"))
            )
            num_pages = math.ceil(float(page_elt.text.split(" ")[4]) / 60)

        # Read holdings data
        if not self.quiet_mode:
            print("{}: page 1 of {} ...".format(etf_symbol, num_pages), end=" ")
        time.sleep(0.5)  # force wait needed for reliability
        dataframe_list = [pd.read_html(driver.page_source)[1]]
        if not self.quiet_mode:
            print("complete")
        current_page = 2
        while current_page <= num_pages:
            if not self.quiet_mode:
                print(
                    "{}: page {} of {} ...".format(etf_symbol, current_page, num_pages),
                    end=" ",
                )
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            next_button = driver.find_element(
                By.XPATH, "//li[@pagenumber='{}']".format(current_page)
            )
            driver.execute_script("arguments[0].click();", next_button)
            while (
                True
            ):  # wait until the new data has loaded (read_html() is from pandas so can't use selenium wait)
                time.sleep(0.25)
                df = pd.read_html(driver.page_source, match="Symbol")[0]
                if not df.equals(dataframe_list[-1]):
                    break
            dataframe_list.append(df)
            current_page += 1
            if not self.quiet_mode:
                print("complete")
        # end while
        concat_result = pd.concat(dataframe_list)  # merge into a single dataframe
        result_df = concat_result.drop_duplicates()
        result_df.columns = [
            "Symbol",
            "Description",
            "Portfolio Weight",
            "Shares Held",
            "Market Value",
        ]
        if self.raw_mode:  # strip symbols and units
            result_df["Portfolio Weight"] = result_df["Portfolio Weight"].apply(
                self._convert_units_to_float
            )
            result_df["Shares Held"] = result_df["Shares Held"].apply(
                self._convert_units_to_float
            )
            result_df["Market Value"] = result_df["Market Value"].apply(
                self._convert_units_to_float
            )
        file_path = f"{self.export_dir}\\{etf_symbol}.csv"
        result_df.to_csv(file_path, index=False)  # create the csv
        if self.log_mode:
            driver.execute_script(
                "window.scrollTo(0, -document.body.scrollHeight);"
            )  # info is at top of page
            header_elt = driver.find_element(
                By.by_xpath, "//div[@modulename='FirstGlance']"
            )
            header_text = header_elt.text.split("\n")
            full_name = (
                header_text[0]
                .split(" {}:".format(etf_symbol))[0]
                .encode("ascii", "ignore")
                .decode()
            )
            last_price = header_text[2].split(" ")[0]
            self.log_entries.append(
                [etf_symbol, full_name, last_price, result_df.shape[0]]
            )
        driver.close()
        if not self.quiet_mode:
            print("{}: {} holdings retrieved\n".format(etf_symbol, result_df.shape[0]))
        return True
        # _get_etf_from_schwab()

    def run_schwab_download(self):
        for symbol in self.etf_symbols:
            if symbol in self.valid_etfs:  # skip duplicates
                continue
            if self._get_etf_from_schwab(symbol):
                self.num_files += 1
                self.valid_etfs.append(symbol)

    def generate_log_file(self):
        if not self.quiet_mode:
            print("Generating log file...", end=" ")
        log_dataframe = pd.DataFrame(
            self.log_entries,
            columns=["Symbol", "Name", "Last Price", "Number of Holdings"],
        )
        log_dataframe.to_csv("etf-log.csv", index=False)
        self.num_files += 1
        if not self.quiet_mode:
            print("complete")

    def print_end_summary(self):
        end_time = time.time()
        elapse = end_time - self.start_time
        print(
            "\n{} file(s) have been generated for {} ETF(s):".format(
                self.num_files, len(self.valid_etfs)
            )
        )
        if self.log_mode:
            print("etf-log.csv")
        for symbol in self.valid_etfs:
            print("{}\\{}.csv".format(self.export_dir, symbol))

        print(f"[Total Elapse]: {elapse:.2f} seconds")


def main():
    export_dir = "M:\\Finance\\etfs"
    downloader = HoldingsDownloader(export_dir)
    downloader.run_schwab_download()
    if downloader.log_mode:
        downloader.generate_log_file()
    if not downloader.quiet_mode:
        downloader.print_end_summary()


if __name__ == "__main__":
    main()
