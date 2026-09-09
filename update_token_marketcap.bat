@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ========================================
echo  FOMO 代币市值更新工具
echo ========================================
echo.
python "%~dp0update_token_marketcap.py"
if errorlevel 1 (
    echo.
    echo [错误] 更新失败，请检查 Python 是否已安装。
    pause
    exit /b 1
)
echo.
echo [完成] CSV 市值列已更新。
pause
