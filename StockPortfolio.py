import tkinter as tk
import json
from pathlib import Path
from tkinter import messagebox, ttk
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


STOCKS = {
	"Apple (AAPL)": "AAPL", "Microsoft (MSFT)": "MSFT", "NVIDIA (NVDA)": "NVDA",
	"Amazon (AMZN)": "AMZN", "Alphabet (GOOGL)": "GOOGL", "Meta (META)": "META",
	"Tesla (TSLA)": "TSLA", "JPMorgan (JPM)": "JPM", "Visa (V)": "V",
	"Walmart (WMT)": "WMT", "Coca-Cola (KO)": "KO", "Netflix (NFLX)": "NFLX",
	"Berkshire Hathaway (BRK-B)": "BRK-B", "AMD (AMD)": "AMD", "Costco (COST)": "COST",
}
BENCHMARKS = {"No benchmark": None, "S&P 500 (^GSPC)": "^GSPC", "Nasdaq 100 (^NDX)": "^NDX", "Dow Jones (^DJI)": "^DJI"}
MONTHS = ["Full year"] + [pd.Timestamp(2000, month, 1).strftime("%B") for month in range(1, 13)]
SIMULATION_PERIODS = pd.period_range(end=pd.Timestamp.today().to_period("M"), periods=24, freq="M")
SIMULATION_MONTHS = [period.strftime("%B %Y") for period in SIMULATION_PERIODS]
PORTFOLIO_FILE = Path(__file__).with_name("portfolio.json")


class MarketDashboard:
	def __init__(self, root):
		self.root = root
		self.root.title("MarketLens | Stock Performance Dashboard")
		self.root.geometry("1000x680")
		self.root.minsize(820, 580)
		self.root.resizable(True, True)
		self.root.configure(bg="#F4F1EA")
		self._configure_style()
		self.summary = None
		self.prices = None
		self.daily_returns = None
		self.normalized_prices = None
		self.analysis_label = ""
		self.live_holdings = {}
		self.live_history = []
		self.live_total_invested = 0.0
		self._refresh_job = None
		self._load_live_portfolio()
		self._build_mode_tabs()
		self._build_controls()
		self._build_tabs()
		self._build_simulation()
		self._build_live_portfolio()
		if self.live_holdings:
			self.root.after(100, self.refresh_live_portfolio)
		self.root.protocol("WM_DELETE_WINDOW", self._close_app)

	def _load_live_portfolio(self):
		if not PORTFOLIO_FILE.exists():
			return
		try:
			with PORTFOLIO_FILE.open("r", encoding="utf-8") as portfolio_file:
				data = json.load(portfolio_file)
			self.live_holdings = data.get("holdings", {})
			self.live_history = [(datetime.fromisoformat(point[0]), point[1], point[2]) for point in data.get("history", [])]
			self.live_total_invested = float(data.get("total_invested", 0.0))
		except (OSError, ValueError, TypeError, json.JSONDecodeError):
			self.live_holdings = {}
			self.live_history = []
			self.live_total_invested = 0.0

	def _save_live_portfolio(self):
		data = {
			"holdings": self.live_holdings,
			"history": [[timestamp.isoformat(), value, invested] for timestamp, value, invested in self.live_history],
			"total_invested": self.live_total_invested,
		}
		try:
			with PORTFOLIO_FILE.open("w", encoding="utf-8") as portfolio_file:
				json.dump(data, portfolio_file, indent=2)
		except OSError as error:
			self.status_var.set(f"Portfolio could not be saved: {error}")

	def _close_app(self):
		if self._refresh_job is not None:
			self.root.after_cancel(self._refresh_job)
			self._refresh_job = None
		self._save_live_portfolio()
		self.root.quit()
		self.root.destroy()

	def _configure_style(self):
		style = ttk.Style(self.root)
		style.theme_use("clam")
		style.configure("App.TFrame", background="#F4F1EA")
		style.configure("TLabel", background="#F4F1EA", foreground="#24323D", font=("Trebuchet MS", 10))
		style.configure("Title.TLabel", background="#F4F1EA", foreground="#24323D", font=("Trebuchet MS", 22, "bold"))
		style.configure("Subtitle.TLabel", background="#F4F1EA", foreground="#60717A", font=("Trebuchet MS", 10))
		style.configure("TLabelframe", background="#FFFFFF", bordercolor="#D8D2C8")
		style.configure("TLabelframe.Label", background="#FFFFFF", foreground="#1F7A72", font=("Trebuchet MS", 10, "bold"))
		style.configure("TNotebook", background="#F4F1EA", borderwidth=0)
		style.configure("TNotebook.Tab", background="#DDD8CE", foreground="#51616A", padding=(16, 8), font=("Trebuchet MS", 10, "bold"))
		style.map("TNotebook.Tab", background=[("selected", "#FFFFFF")], foreground=[("selected", "#1F7A72")])
		style.configure("Tab.TFrame", background="#FFFFFF")
		style.configure("Accent.TButton", background="#1F7A72", foreground="#FFFFFF", padding=(14, 7), font=("Trebuchet MS", 10, "bold"))
		style.map("Accent.TButton", background=[("active", "#D96C4F")])
		style.configure("Treeview", background="#FFFFFF", fieldbackground="#FFFFFF", foreground="#24323D", rowheight=30, font=("Trebuchet MS", 9))
		style.configure("Treeview.Heading", background="#1F7A72", foreground="#FFFFFF", font=("Trebuchet MS", 9, "bold"), padding=7)
		style.map("Treeview", background=[("selected", "#D8EEE9")], foreground=[("selected", "#24323D")])

	def _build_controls(self):
		header = ttk.Frame(self.analysis_mode, style="App.TFrame")
		header.pack(fill="x", padx=16, pady=(14, 4))
		ttk.Label(header, text="MarketLens", style="Title.TLabel").pack(anchor="w")
		ttk.Label(header, text="Compare returns, risk, and relationships across the market", style="Subtitle.TLabel").pack(anchor="w")
		controls = ttk.LabelFrame(self.analysis_mode, text="Analysis controls", padding=10)
		controls.pack(fill="x", padx=12, pady=(4, 6))

		ttk.Label(controls, text="Primary stock").grid(row=0, column=0, sticky="w")
		self.primary_var = tk.StringVar(value="Apple (AAPL)")
		ttk.Combobox(controls, textvariable=self.primary_var, values=list(STOCKS), width=22).grid(row=1, column=0, padx=(0, 14), sticky="w")

		ttk.Label(controls, text="Compare with (tickers separated by commas)").grid(row=0, column=1, columnspan=2, sticky="w")
		self.comparison_var = tk.StringVar(value="MSFT, NVDA")
		self.comparison_entry = ttk.Entry(controls, textvariable=self.comparison_var, width=25)
		self.comparison_entry.grid(row=1, column=1, columnspan=2, padx=4, sticky="w")
		self.comparison_entry.bind("<KeyRelease>", self._update_suggestions)
		self.suggestion_list = tk.Listbox(controls, height=4, width=25, exportselection=False, bg="#FFFFFF", fg="#24323D", selectbackground="#D8EEE9", selectforeground="#24323D", relief="solid", borderwidth=1)
		self.suggestion_list.bind("<<ListboxSelect>>", self._select_suggestion)

		ttk.Label(controls, text="Benchmark").grid(row=0, column=3, sticky="w")
		self.benchmark_var = tk.StringVar(value="S&P 500 (^GSPC)")
		ttk.Combobox(controls, textvariable=self.benchmark_var, values=list(BENCHMARKS), state="readonly", width=20).grid(row=1, column=3, padx=8, sticky="w")

		ttk.Label(controls, text="Period").grid(row=0, column=4, sticky="w")
		self.month_var = tk.StringVar(value="Full year")
		ttk.Combobox(controls, textvariable=self.month_var, values=MONTHS, state="readonly", width=13).grid(row=1, column=4, padx=8, sticky="w")
		ttk.Button(controls, text="Run analysis", style="Accent.TButton", command=self.run_analysis).grid(row=1, column=5, padx=(10, 0), sticky="w")

		self.status_var = tk.StringVar(value="Choose your comparison and run the analysis.")
		ttk.Label(self.analysis_mode, textvariable=self.status_var).pack(anchor="w", padx=14, pady=(0, 5))

	def _build_mode_tabs(self):
		self.mode_tabs = ttk.Notebook(self.root)
		self.mode_tabs.pack(fill="both", expand=True, padx=12, pady=(12, 0))
		self.analysis_mode = ttk.Frame(self.mode_tabs, style="App.TFrame")
		self.simulation_mode = ttk.Frame(self.mode_tabs, style="App.TFrame")
		self.live_mode = ttk.Frame(self.mode_tabs, style="App.TFrame")
		self.mode_tabs.add(self.analysis_mode, text="Analysis")
		self.mode_tabs.add(self.simulation_mode, text="Simulation")
		self.mode_tabs.add(self.live_mode, text="Live portfolio")

	def _update_suggestions(self, event=None):
		search_text = self.comparison_var.get().split(",")[-1].strip().lower()
		matches = [label for label, ticker in STOCKS.items() if search_text in label.lower() or search_text in ticker.lower()]
		self.suggestion_list.delete(0, tk.END)
		for match in matches[:4]:
			self.suggestion_list.insert(tk.END, match)
		if matches and search_text:
			self.suggestion_list.grid(row=2, column=1, columnspan=2, padx=4, sticky="nw")
		else:
			self.suggestion_list.grid_remove()

	def _select_suggestion(self, event=None):
		selection = self.suggestion_list.curselection()
		if not selection:
			return
		label = self.suggestion_list.get(selection[0])
		ticker = STOCKS[label]
		parts = self.comparison_var.get().split(",")
		parts[-1] = f" {ticker}"
		self.comparison_var.set(",".join(parts).strip())
		self.suggestion_list.grid_remove()
		self.comparison_entry.icursor(tk.END)

	def _build_tabs(self):
		self.tabs = ttk.Notebook(self.analysis_mode)
		self.tabs.pack(fill="both", expand=True, padx=12, pady=(0, 12))
		self.summary_tab = ttk.Frame(self.tabs, padding=10, style="Tab.TFrame")
		self.performance_tab = ttk.Frame(self.tabs, style="Tab.TFrame")
		self.risk_tab = ttk.Frame(self.tabs, style="Tab.TFrame")
		self.correlation_tab = ttk.Frame(self.tabs, style="Tab.TFrame")
		for tab, title in ((self.summary_tab, "Summary"), (self.performance_tab, "Performance"), (self.risk_tab, "Risk metrics"), (self.correlation_tab, "Correlation matrix")):
			self.tabs.add(tab, text=title)
		self.table = ttk.Treeview(self.summary_tab, show="headings")
		self.table.tag_configure("even", background="#FFFFFF")
		self.table.tag_configure("odd", background="#F1F7F5")
		self.table.pack(fill="both", expand=True)
		self.performance_selection = "All"
		self.performance_selection_label = None
		self.performance_chart_container = ttk.Frame(self.performance_tab, style="Tab.TFrame")
		self.performance_chart_container.pack(fill="both", expand=True, padx=8, pady=(10, 8))

	def _build_simulation(self):
		investment_controls = ttk.LabelFrame(self.simulation_mode, text="Mock investment", padding=12)
		investment_controls.pack(fill="x", padx=12, pady=12)
		self.investment_stock_var = tk.StringVar(value="Apple (AAPL)")
		self.investment_amount_var = tk.StringVar(value="1000")
		self.investment_start_var = tk.StringVar(value=SIMULATION_MONTHS[0])
		self.investment_end_var = tk.StringVar(value=SIMULATION_MONTHS[-1])
		ttk.Label(investment_controls, text="Stock").grid(row=0, column=0, sticky="w")
		ttk.Combobox(investment_controls, textvariable=self.investment_stock_var, values=list(STOCKS), width=25).grid(row=1, column=0, padx=(0, 14), sticky="w")
		ttk.Label(investment_controls, text="Initial investment ($)").grid(row=0, column=1, sticky="w")
		ttk.Entry(investment_controls, textvariable=self.investment_amount_var, width=18).grid(row=1, column=1, padx=(0, 14), sticky="w")
		ttk.Label(investment_controls, text="Start month").grid(row=0, column=2, sticky="w")
		ttk.Combobox(investment_controls, textvariable=self.investment_start_var, values=SIMULATION_MONTHS, state="readonly", width=15).grid(row=1, column=2, padx=(0, 14), sticky="w")
		ttk.Label(investment_controls, text="End month").grid(row=0, column=3, sticky="w")
		ttk.Combobox(investment_controls, textvariable=self.investment_end_var, values=SIMULATION_MONTHS, state="readonly", width=15).grid(row=1, column=3, padx=(0, 14), sticky="w")
		ttk.Button(investment_controls, text="Simulate investment", style="Accent.TButton", command=self.simulate_investment).grid(row=1, column=4, sticky="w")
		self.investment_result_var = tk.StringVar(value="Choose a stock, amount, and date range to see how the investment would have grown.")
		ttk.Label(self.simulation_mode, textvariable=self.investment_result_var, style="Subtitle.TLabel").pack(anchor="w", padx=14, pady=(0, 4))
		self.investment_chart_frame = ttk.Frame(self.simulation_mode, style="Tab.TFrame")
		self.investment_chart_frame.pack(fill="both", expand=True, padx=8, pady=4)

	def _build_live_portfolio(self):
		controls = ttk.LabelFrame(self.live_mode, text="Paper trading account", padding=12)
		controls.pack(fill="x", padx=12, pady=12)
		self.live_stock_var = tk.StringVar(value="Apple (AAPL)")
		self.live_amount_var = tk.StringVar(value="1000")
		ttk.Label(controls, text="Stock").grid(row=0, column=0, sticky="w")
		ttk.Combobox(controls, textvariable=self.live_stock_var, values=list(STOCKS), width=25).grid(row=1, column=0, padx=(0, 14), sticky="w")
		ttk.Label(controls, text="Fake money to invest ($)").grid(row=0, column=1, sticky="w")
		ttk.Entry(controls, textvariable=self.live_amount_var, width=18).grid(row=1, column=1, padx=(0, 14), sticky="w")
		ttk.Button(controls, text="Buy stock", style="Accent.TButton", command=self.buy_live_stock).grid(row=1, column=2, padx=(0, 8), sticky="w")
		ttk.Button(controls, text="Refresh prices", command=self.refresh_live_portfolio).grid(row=1, column=3, padx=(0, 8), sticky="w")
		ttk.Button(controls, text="Reset account", command=self.reset_live_portfolio).grid(row=1, column=4, sticky="w")
		self.live_invested_var = tk.StringVar(value="$0.00")
		self.live_value_var = tk.StringVar(value="$0.00")
		self.live_profit_var = tk.StringVar(value="$0.00")
		ttk.Label(self.live_mode, text="Prices are downloaded from Yahoo Finance and may be delayed.", style="Subtitle.TLabel").pack(anchor="w", padx=14, pady=(0, 8))
		live_table_frame = ttk.Frame(self.live_mode, style="App.TFrame")
		live_table_frame.pack(fill="x", padx=12, pady=(0, 6))
		self.live_tree = ttk.Treeview(live_table_frame, columns=("Ticker", "Shares", "Average cost", "Price", "Value", "P/L"), show="headings", height=3)
		for column in ("Ticker", "Shares", "Average cost", "Price", "Value", "P/L"):
			self.live_tree.heading(column, text=column)
			self.live_tree.column(column, width=135, anchor="center")
		live_scrollbar = ttk.Scrollbar(live_table_frame, orient="vertical", command=self.live_tree.yview)
		self.live_tree.configure(yscrollcommand=live_scrollbar.set)
		self.live_tree.pack(side="left", fill="x", expand=True)
		live_scrollbar.pack(side="right", fill="y")
		live_body = ttk.Frame(self.live_mode, style="App.TFrame")
		live_body.pack(fill="both", expand=True, padx=8, pady=(0, 12))
		stats = ttk.LabelFrame(live_body, text="Portfolio snapshot", padding=14)
		stats.pack(side="left", fill="y", padx=(4, 10))
		for label, variable in (("Initial invested", self.live_invested_var), ("Current value", self.live_value_var), ("Profit / Loss", self.live_profit_var)):
			ttk.Label(stats, text=label, font=("Trebuchet MS", 10, "bold")).pack(anchor="w", pady=(4, 0))
			ttk.Label(stats, textvariable=variable, font=("Trebuchet MS", 14, "bold"), foreground="#1F7A72").pack(anchor="w", pady=(0, 12))
		self.live_chart_frame = ttk.Frame(live_body, style="Tab.TFrame")
		self.live_chart_frame.pack(side="left", fill="both", expand=True)
		self.root.after(15000, self._auto_refresh_live_portfolio)

	def _ticker_from_value(self, value):
		ticker = STOCKS.get(value.strip(), value.strip().upper())
		if " (" in ticker:
			ticker = ticker.rsplit(" (", 1)[1].rstrip(")")
		return ticker

	def _latest_prices(self, tickers):
		prices = yf.download(tickers, period="5d", interval="1d", auto_adjust=True, progress=False)["Close"]
		if isinstance(prices, pd.Series):
			prices = prices.to_frame(name=tickers[0])
		return prices.ffill().iloc[-1]

	def buy_live_stock(self):
		try:
			ticker = self._ticker_from_value(self.live_stock_var.get())
			amount = float(self.live_amount_var.get().replace(",", "").replace("$", ""))
			if not ticker or amount <= 0:
				raise ValueError("Enter a valid stock and an investment greater than zero.")
			price = self._latest_prices([ticker]).get(ticker)
			if pd.isna(price):
				raise ValueError(f"No current price was found for {ticker}.")
			position = self.live_holdings.setdefault(ticker, {"shares": 0.0, "cost": 0.0})
			position["shares"] += amount / price
			position["cost"] += amount
			self.live_total_invested += amount
			self.refresh_live_portfolio()
		except Exception as error:
			messagebox.showerror("Paper trading error", str(error))

	def refresh_live_portfolio(self):
		if not self.live_holdings:
			self.live_invested_var.set("$0.00")
			self.live_value_var.set("$0.00")
			self.live_profit_var.set("$0.00")
			return
		try:
			prices = self._latest_prices(list(self.live_holdings))
			self.live_tree.delete(*self.live_tree.get_children())
			portfolio_value = 0.0
			for ticker, position in self.live_holdings.items():
				price = prices.get(ticker, np.nan)
				value = position["shares"] * price
				profit_loss = value - position["cost"]
				portfolio_value += value
				self.live_tree.insert("", "end", values=(ticker, f"{position['shares']:.4f}", f"${position['cost'] / position['shares']:,.2f}", f"${price:,.2f}", f"${value:,.2f}", f"${profit_loss:+,.2f}"))
			self.live_invested_var.set(f"${self.live_total_invested:,.2f}")
			self.live_value_var.set(f"${portfolio_value:,.2f}")
			self.live_profit_var.set(f"${portfolio_value - self.live_total_invested:+,.2f}")
			self.live_history.append((datetime.now(), portfolio_value, self.live_total_invested))
			self._show_live_chart()
			self._save_live_portfolio()
		except Exception as error:
			self.status_var.set(f"Live prices unavailable: {error}")

	def reset_live_portfolio(self):
		self.live_holdings.clear()
		self.live_history.clear()
		self.live_total_invested = 0.0
		self.live_tree.delete(*self.live_tree.get_children())
		self.live_invested_var.set("$0.00")
		self.live_value_var.set("$0.00")
		self.live_profit_var.set("$0.00")
		for child in self.live_chart_frame.winfo_children():
			child.destroy()
		self._save_live_portfolio()

	def _show_live_chart(self):
		for child in self.live_chart_frame.winfo_children():
			child.destroy()
		if not self.live_history:
			return
		figure, axis = plt.subplots(figsize=(9, 3.5))
		times = [point[0] for point in self.live_history]
		values = [point[1] for point in self.live_history]
		invested = [point[2] for point in self.live_history]
		axis.plot(times, values, color="#D96C4F", linewidth=2.5, marker=None, label="Portfolio value")
		axis.plot(times, invested, color="#1F7A72", linestyle="--", linewidth=2, marker=None, label="Initial investment")
		axis.margins(y=0.2)
		axis.set_title("Live paper portfolio")
		axis.set_ylabel("Value ($)")
		axis.grid(True, alpha=0.3)
		axis.legend()
		figure.autofmt_xdate()
		figure.tight_layout()
		self._embed_figure(self.live_chart_frame, figure)

	def _auto_refresh_live_portfolio(self):
		if self.live_holdings:
			self.refresh_live_portfolio()
		self._refresh_job = self.root.after(15000, self._auto_refresh_live_portfolio)

	def _selected_tickers(self):
		primary_value = self.primary_var.get().strip()
		primary = STOCKS.get(primary_value, primary_value.upper())
		if " (" in primary:
			primary = primary.rsplit(" (", 1)[1].rstrip(")")
		if not primary:
			raise ValueError("Choose or enter a primary stock ticker.")
		selected = [primary]
		for comparison in self.comparison_var.get().split(","):
			ticker = comparison.strip().upper()
			if " (" in ticker:
				ticker = ticker.rsplit(" (", 1)[1].rstrip(")")
			if ticker and ticker not in selected:
				selected.append(ticker)
		benchmark = BENCHMARKS[self.benchmark_var.get()]
		if benchmark and benchmark not in selected:
			selected.append(benchmark)
		return selected

	def run_analysis(self):
		try:
			selected = self._selected_tickers()
			self.status_var.set("Downloading market data...")
			self.root.update_idletasks()
			prices = yf.download(selected, period="1y", auto_adjust=True, progress=False)["Close"]
			if isinstance(prices, pd.Series):
				prices = prices.to_frame(name=selected[0])
			prices = prices.dropna(axis="columns", how="all").dropna()
			if self.month_var.get() != "Full year":
				month_number = MONTHS.index(self.month_var.get())
				latest_date = prices.index[-1]
				target_year = latest_date.year if month_number <= latest_date.month else latest_date.year - 1
				prices = prices.loc[(prices.index.year == target_year) & (prices.index.month == month_number)]
				self.analysis_label = prices.index.strftime("%B %Y")[0] if not prices.empty else self.month_var.get()
			else:
				self.analysis_label = "the last year"
			if prices.empty or len(prices) < 2:
				raise ValueError("There is not enough price data for that period.")
			self.prices = prices
			self.daily_returns = prices.pct_change().dropna()
			normalized = prices.div(prices.iloc[0]).mul(100)
			self.normalized_prices = normalized
			drawdowns = normalized.div(normalized.cummax()).sub(1)
			self.summary = pd.DataFrame({
				"Start Price ($)": prices.iloc[0],
				"End Price ($)": prices.iloc[-1],
				"Total Return (%)": prices.iloc[-1] / prices.iloc[0] - 1,
				"Annualized Volatility (%)": self.daily_returns.std() * np.sqrt(252),
				"Sharpe Ratio": self.daily_returns.mean() / self.daily_returns.std() * np.sqrt(252),
				"Maximum Drawdown (%)": drawdowns.min(),
				"Best Daily Return (%)": self.daily_returns.max(),
				"Worst Daily Return (%)": self.daily_returns.min(),
			}).sort_values("Total Return (%)", ascending=False)
			self.summary.index.name = "Ticker"
			self._show_summary()
			self._show_performance()
			self._show_risk()
			self._show_correlation()
			self.status_var.set(f"Updated for {self.analysis_label}.")
		except Exception as error:
			self.status_var.set("Analysis could not be completed.")
			messagebox.showerror("Analysis error", str(error))

	def _show_summary(self):
		self.table.delete(*self.table.get_children())
		columns = list(self.summary.columns)
		self.table["columns"] = ["Ticker"] + columns
		for column in ["Ticker"] + columns:
			self.table.heading(column, text=column)
			self.table.column(column, width=145, anchor="center")
		for row_number, (ticker, row) in enumerate(self.summary.iterrows()):
			values = [ticker, f"${row.iloc[0]:,.2f}", f"${row.iloc[1]:,.2f}"] + [f"{value:.2%}" if "Ratio" not in column else f"{value:.2f}" for column, value in zip(columns[2:], row.iloc[2:])]
			self.table.insert("", "end", values=values, tags=("even" if row_number % 2 == 0 else "odd",))

	def _clear_chart(self, tab):
		for child in tab.winfo_children():
			child.destroy()

	def _on_performance_pick(self, event):
		line = event.artist
		selected = line.get_label()
		if selected == self.performance_selection:
			self.performance_selection = "All"
		else:
			self.performance_selection = selected
		self._refresh_performance_selection()

	def _on_performance_blank_click(self, event):
		if self.performance_selection == "All" or event.inaxes != self.performance_axis:
			return
		clicked_line = any(line.contains(event)[0] for line in self.performance_axis.lines)
		if not clicked_line:
			self.performance_selection = "All"
			self._refresh_performance_selection()

	def _refresh_performance_selection(self):
		if not hasattr(self, "performance_axis") or self.performance_axis is None:
			return
		for line in self.performance_axis.lines:
			is_selected = self.performance_selection == "All" or line.get_label() == self.performance_selection
			line.set_alpha(1.0 if is_selected else 0.24)
			line.set_linewidth(3.1 if is_selected else 1.8)
		if self.performance_selection_label is not None:
			self.performance_selection_label.remove()
			self.performance_selection_label = None
		if self.performance_selection != "All":
			self.performance_selection_label = self.performance_axis.text(0.5, 0.93, self.performance_selection, transform=self.performance_axis.transAxes, ha="center", va="bottom", fontsize=11, fontweight="bold", color="#1F7A72")
		self.performance_axis.figure.canvas.draw_idle()

	def _show_performance(self):
		if not hasattr(self, "performance_chart_container"):
			return
		if self.normalized_prices is None:
			return
		if not hasattr(self, "performance_figure") or self.performance_figure is None:
			self.performance_figure, self.performance_axis = plt.subplots(figsize=(10, 5.5))
			self.performance_canvas = FigureCanvasTkAgg(self.performance_figure, master=self.performance_chart_container)
			self.performance_canvas.get_tk_widget().pack(fill="both", expand=True)
			self.performance_canvas.mpl_connect("pick_event", self._on_performance_pick)
			self.performance_canvas.mpl_connect("button_press_event", self._on_performance_blank_click)
		else:
			self.performance_axis.clear()
		colors = plt.get_cmap("tab10").colors
		for index, column in enumerate(self.normalized_prices.columns):
			line, = self.performance_axis.plot(self.normalized_prices.index, self.normalized_prices[column], linewidth=3.1, alpha=1.0, color=colors[index % len(colors)], label=column, picker=True, pickradius=8)
			line.set_pickradius(8)
		self.performance_axis.margins(y=0.2)
		self.performance_axis.set_title(f"Growth of $100 for {self.analysis_label}")
		self.performance_axis.set_ylabel("Portfolio value ($)")
		self.performance_axis.grid(True, alpha=0.3)
		self.performance_axis.legend(title="Ticker")
		self.performance_figure.tight_layout()
		self._refresh_performance_selection()
		self.performance_canvas.draw_idle()

	def _show_risk(self):
		self._clear_chart(self.risk_tab)
		metrics = [("Annualized Volatility (%)", "Annualized Volatility"), ("Sharpe Ratio", "Sharpe Ratio"), ("Maximum Drawdown (%)", "Maximum Drawdown"), ("Best Daily Return (%)", "Best Daily Return"), ("Worst Daily Return (%)", "Worst Daily Return")]
		figure, axes = plt.subplots(2, 3, figsize=(10, 5.5))
		for axis, (metric, title) in zip(axes.flat, metrics):
			self.summary[metric].plot(kind="bar", ax=axis, color="#4472C4")
			axis.set_title(title)
			axis.set_xlabel("")
			axis.tick_params(axis="x", rotation=45)
			axis.grid(axis="y", alpha=0.3)
		axes.flat[-1].set_visible(False)
		figure.suptitle(f"Risk metrics for {self.analysis_label}")
		figure.tight_layout()
		self._embed_figure(self.risk_tab, figure)

	def _show_correlation(self):
		self._clear_chart(self.correlation_tab)
		correlation = self.daily_returns.corr()
		figure, axis = plt.subplots(figsize=(7, 5.5))
		heatmap = axis.imshow(correlation, cmap="coolwarm", vmin=-1, vmax=1)
		axis.set_xticks(range(len(correlation.columns)), correlation.columns, rotation=45, ha="right")
		axis.set_yticks(range(len(correlation.index)), correlation.index)
		axis.set_title(f"Daily return correlation for {self.analysis_label}")
		for row in range(len(correlation.index)):
			for column in range(len(correlation.columns)):
				axis.text(column, row, f"{correlation.iloc[row, column]:.2f}", ha="center", va="center")
		figure.colorbar(heatmap, ax=axis, label="Correlation")
		figure.tight_layout()
		self._embed_figure(self.correlation_tab, figure)

	def simulate_investment(self):
		try:
			stock_value = self.investment_stock_var.get().strip()
			ticker = STOCKS.get(stock_value, stock_value.upper())
			if " (" in ticker:
				ticker = ticker.rsplit(" (", 1)[1].rstrip(")")
			amount = float(self.investment_amount_var.get().replace(",", "").replace("$", ""))
			if amount <= 0:
				raise ValueError("The initial investment must be greater than zero.")
			self.status_var.set(f"Downloading {ticker} investment data...")
			self.root.update_idletasks()
			prices = yf.download([ticker], period="2y", auto_adjust=True, progress=False)["Close"]
			if isinstance(prices, pd.DataFrame):
				prices = prices.iloc[:, 0]
			prices = prices.dropna()
			start_period = SIMULATION_PERIODS[SIMULATION_MONTHS.index(self.investment_start_var.get())]
			end_period = SIMULATION_PERIODS[SIMULATION_MONTHS.index(self.investment_end_var.get())]
			if start_period > end_period:
				raise ValueError("The start month must be before or equal to the end month.")
			price_months = prices.index.to_period("M")
			period_prices = prices.loc[(price_months >= start_period) & (price_months <= end_period)]
			if len(period_prices) < 2:
				raise ValueError("There is not enough price data for that starting month.")
			shares = amount / period_prices.iloc[0]
			investment_values = period_prices * shares
			final_value = investment_values.iloc[-1]
			return_value = final_value / amount - 1
			self.investment_result_var.set(f"${amount:,.2f} invested in {ticker} became ${final_value:,.2f} ({return_value:+.2%}) from {period_prices.index[0].strftime('%B %Y')} to {period_prices.index[-1].strftime('%B %Y')}.")
			for child in self.investment_chart_frame.winfo_children():
				child.destroy()
			figure, axis = plt.subplots(figsize=(9, 4.5))
			investment_values.plot(ax=axis, linewidth=2.5, color="#D96C4F")
			axis.axhline(amount, color="#1F7A72", linestyle="--", label="Initial investment")
			axis.margins(y=0.2)
			axis.set_title(f"{ticker} investment growth")
			axis.set_ylabel("Investment value ($)")
			axis.grid(True, alpha=0.3)
			axis.legend()
			figure.tight_layout()
			self._embed_figure(self.investment_chart_frame, figure)
			self.status_var.set("Investment simulation complete.")
		except Exception as error:
			self.status_var.set("Investment simulation could not be completed.")
			messagebox.showerror("Investment error", str(error))

	def _embed_figure(self, tab, figure):
		canvas = FigureCanvasTkAgg(figure, master=tab)
		canvas.draw()
		canvas.get_tk_widget().pack(fill="both", expand=True)


if __name__ == "__main__":
	root = tk.Tk()
	app = MarketDashboard(root)
	root.mainloop()