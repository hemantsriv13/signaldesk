@echo off
setlocal
cd /d "%~dp0..\web"
call npm ci --no-fund --no-audit || exit /b 1
call npm run android:sync || exit /b 1
cd android
call gradlew.bat assembleDebug || exit /b 1
echo Standalone testing APK: web\android\app\build\outputs\apk\debug\app-debug.apk
echo No Expo Go or Metro server is required. Install only on your own test device.
