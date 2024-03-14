@echo off
cd /d %~dp0
call runtime python -s horde-scribe-bridge.sh %*
