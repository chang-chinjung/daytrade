
# Windows Python 3.14 解決 lxml 編譯問題 (若堅持要裝 finmind 套件版)

# 方法A (推薦)：不用 finmind 套件，改用輕量版
pip install requests yfinance pandas pyarrow
python fetch_real_1min_light.py --stocks 2330 --start 2023-01-01 --end 2023-12-31

# 方法B：強行裝新版 lxml 再裝 finmind 不檢查依賴
pip install --upgrade lxml
pip install finmind --no-deps
pip install requests pydantic aiohttp ta pyecharts ipython loguru tqdm nest-asyncio

# 方法C：降 Python 到 3.11 / 3.12，lxml 4.9.4 有預編輪子
