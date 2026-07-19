param(
  [string]$RepoUrl = "",
  [string]$CommitMsg = "feat: 66->32 filter passed + yfinance fallback + Fugle raw fix"
)

$root = Get-Location
Write-Host "[0] Current dir $root"

# 1. overwrite old screen_stocks.py with final version if exists
if (Test-Path "./screen_stocks_final.py") {
  Copy-Item ./screen_stocks_final.py ./screen_stocks.py -Force
  Write-Host "[1] Overwrote screen_stocks.py with screen_stocks_final.py"
}

# 2. .gitignore
@"
__pycache__/
*.pyc
venv/
.env
*.log
data/*.parquet
data/*.csv
!data/intraday_candidates.csv
data/stock_meta/
reports/
*.zip
config/
fugle.json
"@ | Set-Content .gitignore -Encoding utf8
Write-Host "[2] .gitignore created"

# 3. README
@"
# intraday_lab_full - Task3 pass

## Results
- yfinance 100 -> 66 stocks ok (3707 delisted)
- filter 66 -> 32 stocks (target 30-50)
  min_vol 5000, min_amp 3%

## Run order
python fetch_all_market_daily_v3.py --start 2022-01-01 --out ./data/tw_market_daily_all.parquet --max_stocks 100
python screen_stocks_final.py --input ./data/tw_market_daily_all.parquet --min_vol 5000 --min_amp 0.03 --top_n 50
python fetch_fugle_raw_v3_fixed.py --input ./data/intraday_candidates.csv --start 2024-06-03 --end 2024-06-07 --out ./data/tw_1min_real.parquet --sleep 1.1

FUGLE_API_KEY must be in env, not committed.
"@ | Set-Content README.md -Encoding utf8
Write-Host "[3] README.md created"

# 4. git init
if (-not (Test-Path ".git")) {
  git init
}
git add .
git status
git commit -m "$CommitMsg"
if ($LASTEXITCODE -ne 0) {
  git add -A
  git commit -m "$CommitMsg"
}

# 5. push
if ($RepoUrl -eq "") {
  Write-Host ""
  Write-Host "[NEXT] Create empty repo on GitHub, then run:"
  Write-Host "  git branch -M main"
  Write-Host "  git remote add origin https://github.com/YOUR/REPO.git"
  Write-Host "  git push -u origin main"
  Write-Host ""
  Write-Host "Or run: .\push_to_github_ascii.ps1 -RepoUrl https://github.com/YOUR/REPO.git"
} else {
  $hasOrigin = git remote | Select-String "origin"
  if (-not $hasOrigin) {
    git remote add origin $RepoUrl
  } else {
    git remote set-url origin $RepoUrl
  }
  git branch -M main
  git push -u origin main
  Write-Host "[PASS] Pushed to $RepoUrl"
}
