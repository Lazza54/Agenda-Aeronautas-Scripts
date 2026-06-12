@echo off
cd /d "%~dp0"
REM ============================================================================
REM Script de Geracao de Todos os Relatorios PDF
REM Executa todos os scripts de relatorio em sequencia
REM ============================================================================

echo ========================================================================
echo GERACAO DE RELATORIOS PDF
echo ========================================================================
echo.

REM Definir caminho padrao do Python
set "PYTHON_PATH=D:\ProgramData\anaconda3\python.exe"

REM Verificar se o Python existe
if not exist "%PYTHON_PATH%" (
    echo ERRO: Python nao encontrado em %PYTHON_PATH%
    echo Verifique a instalacao do Anaconda em D:\ProgramData\anaconda3
    pause
    exit /b 1
)

echo Interpretador Python: %PYTHON_PATH%
echo Diretorio de execucao: %CD%
echo.

echo [1/11] Gerando Relatorio de Apresentacao...
"%PYTHON_PATH%" "RELATORIO APRESENTACAO.py"
if errorlevel 1 (
    echo ERRO - Relatorio Apresentacao
    pause
    exit /b 1
)
echo.

echo [2/11] Gerando Relatorio de Corte...
"%PYTHON_PATH%" "RELATORIO CORTE.py"
if errorlevel 1 (
    echo ERRO - Relatorio Corte
    pause
    exit /b 1
)
echo.

echo [3/11] Gerando Relatorio de Jornada...
"%PYTHON_PATH%" "RELATORIO JORNADA.py"
if errorlevel 1 (
    echo ERRO - Relatorio Jornada
    pause
    exit /b 1
)
echo.

echo [4/11] Gerando Relatorio de Operacao...
"%PYTHON_PATH%" "RELATORIO OPERACAO.py"
if errorlevel 1 (
    echo ERRO - Relatorio Operacao
    pause
    exit /b 1
)
echo.

echo [5/11] Gerando Relatorio de Plantao...
"%PYTHON_PATH%" "RELATORIO PLANTAO.py"
if errorlevel 1 (
    echo ERRO - Relatorio Plantao
    pause
    exit /b 1
)
echo.

echo [6/11] Gerando Relatorio de Repouso...
"%PYTHON_PATH%" "RELATORIO REPOUSO.py"
if errorlevel 1 (
    echo ERRO - Relatorio Repouso
    pause
    exit /b 1
)
echo.

echo [7/11] Gerando Relatorio de Repouso Extra...
"%PYTHON_PATH%" "RELATORIO REPOUSO EXTRA.py"
if errorlevel 1 (
    echo ERRO - Relatorio Repouso Extra
    pause
    exit /b 1
)
echo.

echo [8/11] Gerando Relatorio de Reservas...
"%PYTHON_PATH%" "RELATORIO RESERVAS.py"
if errorlevel 1 (
    echo ERRO - Relatorio Reservas
    pause
    exit /b 1
)
echo.

echo [9/11] Gerando Relatorio de Tempo em Solo...
"%PYTHON_PATH%" "RELATORIO TEMPO EM SOLO.py"
if errorlevel 1 (
    echo ERRO - Relatorio Tempo em Solo
    pause
    exit /b 1
)
echo.

echo [10/11] Gerando Relatorio de Treinamento...
"%PYTHON_PATH%" "RELATORIO TREINAMENTO.py"
if errorlevel 1 (
    echo ERRO - Relatorio Treinamento
    pause
    exit /b 1
)
echo.

echo [11/11] Gerando Relatorio de Tempo Solo Detalhado...
"%PYTHON_PATH%" "RELATORIO TEMPO SOLO DETALHADO.py"
if errorlevel 1 (
    echo ERRO - Relatorio Tempo Solo Detalhado
    pause
    exit /b 1
)
echo.
echo ========================================================================
echo GERACAO DE RELATORIOS CONCLUIDA COM SUCESSO!
echo ========================================================================
echo.
echo Todos os relatorios PDF foram gerados com sucesso.
echo.
pause
