param(
  [string]$RepoUrl = "",
  [string]$CommitMsg = "feat: 66->32 篩選通關 + yfinance fallback + Fugle raw fix 達標版"
)

# 0. 檢查路徑
$root = Get-Location
Write-Host "[0] 目前路徑 $root"

# 1. 先把會通的 final 蓋回正式檔 (你現在通的是 screen_stocks_final.py)
if (Test-Path "./screen_stocks_final.py") {
  Copy-Item ./screen_stocks_final.py ./screen_stocks.py -Force
  Write-Host "[1] 已用 screen_stocks_final.py 蓋掉舊 screen_stocks.py"
}

# 2. 產生 .gitignore (大檔不上 GitHub)
@"
# Python
__pycache__/
*.py[cod]
venv/
.env
*.log

# Data 太大不推，只留範例
data/*.parquet
data/*.csv
!data/intraday_candidates.csv
data/stock_meta/
reports/
*.zip

# Keys
config/
fugle.json
"@ | Set-Content .gitignore -Encoding utf8
Write-Host "[2] .gitignore 已產生"

# 3. 產生 README 達標紀錄
@"
# intraday_lab_full - Task3 達標版

## 達標紀錄
- yfinance 抓 100 檔 -> 66 檔成功 (3707下市)
  shape=(72441, 7)
- 篩選 66 -> 32 檔 (目標 30~50 達標)
  條件: min_vol 5000張, min_amp 3%

## 執行順序
\`\`\`powershell
python fetch_all_market_daily_v3.py --start 2022-01-01 --out ./data/tw_market_daily_all.parquet --max_stocks 100
python screen_stocks_final.py --input ./data/tw_market_daily_all.parquet --min_vol 5000 --min_amp 0.03 --top_n 50
python fetch_fugle_raw_v3_fixed.py --input ./data/intraday_candidates.csv --start 2024-06-03 --end 2024-06-07 --out ./data/tw_1min_real.parquet --sleep 1.1
\`\`\`

## 重要
FUGLE_API_KEY 請用 env，不要 commit
\`\$env:FUGLE_API_KEY="你的key"\`
"@ | Set-Content README.md -Encoding utf8
Write-Host "[3] README.md 已產生"

# 4. git init
if (-not (Test-Path ".git")) {
  git init
}
git add .
git status
git commit -m "$CommitMsg" 2>$null
if ($LASTEXITCODE -ne 0) {
  git add -A
  git commit -m "$CommitMsg"
}

# 5. 推上 GitHub
if ($RepoUrl -eq "") {
  Write-Host "`n[下一步] 請去 GitHub 新建一個空 repo，然後執行："
  Write-Host "  git branch -M main"
  Write-Host "  git remote add origin https://github.com/你的帳號/你的repo.git"
  Write-Host "  git push -u origin main`n"
  Write-Host "或直接帶網址跑： .\push_to_github.ps1 -RepoUrl https://github.com/你的帳號/你的repo.git"
} else {
  if (-not (git remote | Select-String "origin")) {
    git remote add origin $RepoUrl
  } else {
    git remote set-url origin $RepoUrl
  }
  git branch -M main
  git push -u origin main
  Write-Host "[PASS] 已推上 $RepoUrl"
}
