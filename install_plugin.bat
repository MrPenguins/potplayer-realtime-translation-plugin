@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul

echo ===================================================
echo   PotPlayer DSP Plugin - Auto Installer
echo ===================================================

cd /d "%~dp0"

:: 1. 尝试使用 CMake 编译 DLL (如果存在)
echo [状态] 正在寻找 CMake 并尝试编译底层 C++ 拦截器...
where cmake >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [警告] 找不到 CMake。如果你是从官方 Release 页面下载了预编译的 dll，可忽略此步骤。
) else (
    cd dsp_plugin
    if not exist "build" mkdir build
    cd build
    cmake .. >nul
    cmake --build . --config Release >nul
    if !ERRORLEVEL! EQU 0 (
        echo [成功] C++ DSP 插件编译成功！
    ) else (
        echo [警告] 编译失败，可能是由于缺少 Visual Studio C++ 构建工具。
    )
    cd ../..
)

:: 检查是否存在编译好的 DLL (预编译的或者刚刚编译出来的)
set "dllPath=dsp_plugin\build\Release\dsp_whisper.dll"
if not exist "%dllPath%" (
    echo [错误] 找不到编译好的插件文件 "%dllPath%"。请确保你有预编译的文件。
    pause
    exit /b
)

:: 2. 从注册表自动寻找 PotPlayer 安装路径
echo [状态] 正在自动寻找 PotPlayer 安装路径...
set "PotPlayerPath="

:: 尝试查找 64位
for /f "tokens=2*" %%a in ('reg query "HKEY_LOCAL_MACHINE\SOFTWARE\DAUM\PotPlayer64" /v "ProgramPath" 2^>nul') do (
    set "PotPlayerPath=%%b"
)

:: 如果没找到，尝试查找 32位
if not defined PotPlayerPath (
    for /f "tokens=2*" %%a in ('reg query "HKEY_LOCAL_MACHINE\SOFTWARE\DAUM\PotPlayer" /v "ProgramPath" 2^>nul') do (
        set "PotPlayerPath=%%b"
    )
)

:: 从 ProgramPath 中截取出目录路径
if defined PotPlayerPath (
    for %%I in ("!PotPlayerPath!") do set "PotPlayerDir=%%~dpI"
    echo [发现] 找到 PotPlayer: !PotPlayerDir!
) else (
    :: 回退机制，尝试默认路径
    if exist "C:\Program Files\DAUM\PotPlayer\PotPlayer64.exe" set "PotPlayerDir=C:\Program Files\DAUM\PotPlayer\"
    if exist "C:\Program Files (x86)\DAUM\PotPlayer\PotPlayer.exe" set "PotPlayerDir=C:\Program Files (x86)\DAUM\PotPlayer\"
)

if not defined PotPlayerDir (
    echo [错误] 无法在注册表或默认路径中找到 PotPlayer。请手动将 %dllPath% 复制到你的 PotPlayer\Plugins\Audio 目录。
    pause
    exit /b
)

:: 3. 复制 DLL 到 Plugins\Audio 文件夹
set "PluginDir=!PotPlayerDir!Plugins\Audio"
if not exist "!PluginDir!" mkdir "!PluginDir!"

echo [状态] 正在将插件复制到: "!PluginDir!"
copy /y "%dllPath%" "!PluginDir!\dsp_whisper.dll" >nul

if %ERRORLEVEL% EQU 0 (
    echo [成功] 插件安装完毕！
    echo.
    echo 下一步操作：
    echo 请打开 PotPlayer -^> 选项 (F5) -^> 声音 -^> 声音处理 -^> Winamp DSP 插件。
    echo 勾选“启用”，并在下拉列表中选择 "Whisper Interceptor Plugin"。
) else (
    echo [错误] 复制失败！可能是权限不足，请右键选择“以管理员身份运行”此脚本。
)

echo.
pause
