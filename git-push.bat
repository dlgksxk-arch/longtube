@echo off
echo ========================================
echo  LongTube Git Push - v2.0.1
echo ========================================

cd /d "%~dp0"

if exist ".git" (
    echo Removing existing .git folder...
    rmdir /s /q .git
)

echo Initializing git...
git init -b main
git config user.email "dlgksxk@gmail.com"
git config user.name "Jevis"
git add -A
git commit -m "v2.0.1: fix studio spend_ledger + generate-async validation"
git tag v2.0.1

echo Setting remote...
git remote add origin https://github.com/dlgksxk-arch/longtube.git

echo Pushing...
git push -u origin main --force --tags

echo ========================================
echo  v2.0.1 push complete!
echo ========================================
pause
