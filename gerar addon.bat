@echo off
REM Entrar na pasta do projeto
cd /d "C:\CAMINHO\DO\PROJETO\calendario_simples_BR"

REM Atualizar o pip
"C:\Users\LEANDROSOUZA\AppData\Local\Programs\Python\Python313\python.exe" -m pip install -U pip

REM Instalar dependências necessárias
"C:\Users\LEANDROSOUZA\AppData\Local\Programs\Python\Python313\python.exe" -m pip install -U --user scons
"C:\Users\LEANDROSOUZA\AppData\Local\Programs\Python\Python313\python.exe" -m pip install -U --user markdown

REM Gerar o pacote .nvda-addon
"C:\Users\LEANDROSOUZA\AppData\Roaming\Python\Python313\Scripts\scons.exe" -Q

echo.
echo ============================================
echo Addon gerado com sucesso!
echo ============================================
pause
