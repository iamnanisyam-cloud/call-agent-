# Quick start script for the voice assistant
# Run this in PowerShell from the project folder

Write-Host "Activating virtual environment..."
.\.venv\Scripts\Activate.ps1

Write-Host "Setting test language to Telugu..."
$env:TEST_LANGUAGE = "te"

Write-Host "Running console test (Telugu via Sarvam)..."
.\.venv\Scripts\python agent.py console

# To run in English instead:
# $env:TEST_LANGUAGE = "en"
# python agent.py console

# For real calls (after trunk is set):
# python make_call.py --to +918074835456 --language te --purpose "Test Telugu with Sarvam"
