@echo off
cd /d "%~dp0"
REM ============================================================================
REM Script de Processamento Completo de Dados de Aeronautas
REM Executa todos os scripts em sequência
REM ============================================================================

echo ========================================================================
echo PROCESSAMENTO COMPLETO DE DADOS DE AERONAUTAS
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

echo ========================================================================
echo ROTINA INICIAL DE SELECAO DE ENTRADA E SAIDA
echo ========================================================================
echo.

set "ESCALA_DIR="
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description = 'Selecione o diretorio onde esta o PDF da escala'; if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){$d.SelectedPath}"`) do set "ESCALA_DIR=%%I"

if not defined ESCALA_DIR (
    echo ERRO: Diretorio de escala nao selecionado.
    pause
    exit /b 1
)

set "ESCALA_PDF="
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; $o = New-Object System.Windows.Forms.OpenFileDialog; $o.Title = 'Selecione o arquivo PDF da escala'; $o.Filter = 'Arquivos PDF (*.pdf)|*.pdf|Todos os arquivos (*.*)|*.*'; $o.InitialDirectory = '%ESCALA_DIR%'; if($o.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){$o.FileName}"`) do set "ESCALA_PDF=%%I"

if not defined ESCALA_PDF (
    echo ERRO: Arquivo PDF da escala nao selecionado.
    pause
    exit /b 1
)

set "DIR_SAIDA="
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description = 'Selecione o diretorio de saida para CSV e PDF gerados'; if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){$d.SelectedPath}"`) do set "DIR_SAIDA=%%I"

if not defined DIR_SAIDA (
    echo ERRO: Diretorio de saida nao selecionado.
    pause
    exit /b 1
)

set "AERO_ESCALA_INPUT_DIR=%ESCALA_DIR%"
set "AERO_ESCALA_PDF=%ESCALA_PDF%"
set "AERO_OUTPUT_DIR=%DIR_SAIDA%"

echo Diretorio da escala: %AERO_ESCALA_INPUT_DIR%
echo PDF da escala:      %AERO_ESCALA_PDF%
echo Diretorio de saida: %AERO_OUTPUT_DIR%
echo.

echo ========================================================================
echo SELECIONE O TIPO DE ESCALA PARA IMPORTACAO:
echo ========================================================================
echo.
echo [1] ESCALA SABRE (PASSO 1A)
echo [2] ESCALA RESUMIDA (PASSO 1)
echo [3] CIVI ELETRONICA (PASSO 1B)
echo.
set /p OPCAO_ESCALA="Digite sua opcao (1, 2 ou 3): "
echo.

if "%OPCAO_ESCALA%"=="1" (
    echo [1/14] Importando Escala PDF SABRE...
    "%PYTHON_PATH%" "IMPORTA ESCALA PDF SABRE AZUL 19082025 PASSO 1A.py"
    if errorlevel 1 (
        echo ERRO no Passo 1A - Importacao SABRE
        pause
        exit /b 1
    )
    echo.
) else if "%OPCAO_ESCALA%"=="2" (
    echo [1/14] Importando Escala PDF Simplificada...
    "%PYTHON_PATH%" "IMPORTA ESCALA PDF SIMPLIFICADA AZUL 19082025 PASSO 1.py"
    if errorlevel 1 (
        echo ERRO no Passo 1 - Importacao Simplificada
        pause
        exit /b 1
    )
    echo.
) else if "%OPCAO_ESCALA%"=="3" (
    echo [1/14] Importando Escala PDF CIVI Eletronica...
    "%PYTHON_PATH%" "IMPORTA ESCALA PDF CIV PASSO 1.py"
    if errorlevel 1 (
        echo ERRO no Passo 1B - Importacao CIVI Eletronica
        pause
        exit /b 1
    )
    echo.
) else (
    echo ERRO: Opcao invalida! Digite 1, 2 ou 3.
    pause
    exit /b 1
)

echo [2/14] Compondo Check-in e Check-out...
"%PYTHON_PATH%" "COMPOEM Checkin e Checkout PASSO 2.py"
if errorlevel 1 (
    echo ERRO no Passo 2 - Composicao
    pause
    exit /b 1
)
echo.

echo [3/14] Adicionando Sufixo na Coluna Id_Leg...
"%PYTHON_PATH%" "ADICIONA SUFIXO NA COLUNA Id_Leg PASSO 3.py"
if errorlevel 1 (
    echo ERRO no Passo 3 - Adicao de Sufixo
    pause
    exit /b 1
)
echo.

echo [4/14] Calculando Valores Iniciais...
"%PYTHON_PATH%" "CALCULOS VALORES INICIAIS 22082025 PASSO 4.py"
if errorlevel 1 (
    echo ERRO no Passo 4 - Calculos Iniciais
    pause
    exit /b 1
)
echo.

echo [5/14] Criando Valores Finais - Apresentacao...
"%PYTHON_PATH%" "CRIA VALORES FINAIS APRESENTACAO.py"
if errorlevel 1 (
    echo ERRO - Valores Finais Apresentacao
    pause
    exit /b 1
)
echo.

echo [6/14] Criando Valores Finais - Corte...
"%PYTHON_PATH%" "CRIA VALORES FINAIS CORTE.py"
if errorlevel 1 (
    echo ERRO - Valores Finais Corte
    pause
    exit /b 1
)
echo.

echo [7/14] Criando Valores Finais - Jornada...
"%PYTHON_PATH%" "CRIA VALORES FINAIS JORNADA.py"
if errorlevel 1 (
    echo ERRO - Valores Finais Jornada
    pause
    exit /b 1
)
echo.

echo [8/14] Criando Valores Finais - Operacao...
"%PYTHON_PATH%" "CRIA VALORES FINAIS OPERACAO.py"
if errorlevel 1 (
    echo ERRO - Valores Finais Operacao
    pause
    exit /b 1
)
echo.

echo [9/14] Criando Valores Finais - Plantao...
"%PYTHON_PATH%" "CRIA VALORES FINAIS PLANTAO.py"
if errorlevel 1 (
    echo ERRO - Valores Finais Plantao
    pause
    exit /b 1
)
echo.

echo [10/14] Criando Valores Finais - Repouso...
"%PYTHON_PATH%" "CRIA VALORES FINAIS REPOUSO.py"
if errorlevel 1 (
    echo ERRO - Valores Finais Repouso
    pause
    exit /b 1
)
echo.

echo [11/14] Criando Valores Finais - Repouso Extra...
"%PYTHON_PATH%" "CRIA VALORES FINAIS REPOUSO EXTRA.py"
if errorlevel 1 (
    echo ERRO - Valores Finais Repouso Extra
    pause
    exit /b 1
)
echo.

echo [12/14] Criando Valores Finais - Reserva...
"%PYTHON_PATH%" "CRIA VALORES FINAIS RESERVA.py"
if errorlevel 1 (
    echo ERRO - Valores Finais Reserva
    pause
    exit /b 1
)
echo.

echo [13/14] Criando Valores Finais - Tempo Solo...
"%PYTHON_PATH%" "CRIA VALORES FINAIS TEMPO SOLO.py"
if errorlevel 1 (
    echo ERRO - Valores Finais Tempo Solo
    pause
    exit /b 1
)
echo.

echo [14/14] Criando Valores Finais - Treinamento...
"%PYTHON_PATH%" "CRIA VALORES FINAIS TREINAMENTO.py"
if errorlevel 1 (
    echo ERRO - Valores Finais Treinamento
    pause
    exit /b 1
)
echo.

echo ========================================================================
echo PROCESSAMENTO CONCLUIDO COM SUCESSO!
echo ========================================================================
echo.
echo Todos os scripts foram executados com sucesso.
echo Os arquivos CSV de saida foram gerados no diretorio de saida.
echo.
pause
