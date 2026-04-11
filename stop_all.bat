@echo off
title Stop All

echo Stopping RAG Chatbot processes...

taskkill /F /IM "python.exe" /FI "WINDOWTITLE eq RAG*" > nul 2>&1
taskkill /F /IM "python.exe" /FI "WINDOWTITLE eq Cloud*" > nul 2>&1

echo Done.
pause
