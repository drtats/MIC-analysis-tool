@echo off
echo Starting MIC Analysis Tool...
echo.
echo Make sure you have installed the requirements:
echo pip install -r requirements.txt
echo.
streamlit run app.py --server.port 8502
pause
