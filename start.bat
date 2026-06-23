@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul

echo ===================================================
echo   PotPlayer Real-time Translation Plugin - Launcher
echo ===================================================
echo.

cd /d "%~dp0"

:: 检查 Python 环境
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 找不到 Python。请前往 python.org 安装 Python 3.10 或以上版本，并勾选 "Add to PATH"。
    pause
    exit /b
)

:: 隔离环境：检查是否存在 venv
if not exist "backend\venv" (
    echo [状态] 首次运行，正在创建隔离的 Python 虚拟环境...
    python -m venv backend\venv
    if !ERRORLEVEL! NEQ 0 (
        echo [错误] 无法创建虚拟环境。
        pause
        exit /b
    )
    echo [状态] 虚拟环境创建成功。
)

:: 激活虚拟环境并安装依赖
echo [状态] 检查并更新依赖包...
call backend\venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
pip install -r backend\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet

:: 检查配置文件
if not exist "backend\config.yaml" (
    echo [警告] 未找到 backend\config.yaml，将使用默认配置。
    echo         如需自定义设置，请编辑 backend\config.yaml。
) else (
    echo [状态] 配置文件 backend\config.yaml 已就绪。
)

:: 检查翻译后端配置并给出提示
echo.
echo 翻译后端提示：
echo   - 如果使用 API 模式，请设置环境变量：set TRANSLATION_API_KEY=your-key
echo   - 如果使用 Ollama 本地模式，请确保 Ollama 正在运行 (ollama serve)
echo   - 如果不需要翻译 (仅转写)，请在 config.yaml 中设置 backend: none
echo   - 详细配置请编辑 backend\config.yaml
echo.

:: 启动服务
echo [状态] 正在启动 Whisper 翻译核心和透明字幕层...
echo.

start "Whisper Translation Server" cmd /c "call backend\venv\Scripts\activate.bat && cd backend && python server.py"
start "Subtitle Overlay" cmd /c "call backend\venv\Scripts\activate.bat && cd backend && python overlay.py"

echo [成功] 服务已在后台启动！
echo.
echo 注意事项：
echo 1. 首次运行 Whisper 会自动下载模型文件（约 1-3 GB），请保持网络畅通。
echo 2. 请在 PotPlayer 选项中启用 "Whisper Interceptor Plugin" DSP 插件。
echo 3. 翻译悬浮窗会自动贴近屏幕下方。
echo 4. 如需热更新配置，访问 http://127.0.0.1:5000/config
echo 5. 如需查看健康状态，访问 http://127.0.0.1:5000/health
echo.
pause
