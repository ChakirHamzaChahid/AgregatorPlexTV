@echo off
REM test-runner.bat - Script de lancement des tests pour Windows
REM
REM Usage:
REM   test-runner.bat              # Tous les tests rapides
REM   test-runner.bat all          # Tous les tests (y compris slow)
REM   test-runner.bat coverage     # Avec rapport de couverture
REM   test-runner.bat debug        # Mode débogage verbose
REM   test-runner.bat integration  # Seulement tests intégration
REM   test-runner.bat endpoints    # Seulement tests endpoints
REM   test-runner.bat movies       # Seulement tests films/séries
REM   test-runner.bat streaming    # Seulement tests streaming
REM   test-runner.bat single <test> # Un test spécifique
REM   test-runner.bat help         # Afficher l'aide
REM

setlocal enabledelayedexpansion

REM Vérifier si pytest est installé
where pytest >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] pytest non installé!
    echo.
    echo Installation: pip install -r requirements-test.txt
    echo.
    exit /b 1
)

echo.
echo [OK] pytest trouvé
echo.

REM Récupérer le paramètre (par défaut: fast)
set MODE=%1
if "%MODE%"=="" set MODE=fast

REM Exécuter selon le mode
if /i "%MODE%"=="fast" goto run_fast
if /i "%MODE%"=="all" goto run_all
if /i "%MODE%"=="coverage" goto run_coverage
if /i "%MODE%"=="debug" goto run_debug
if /i "%MODE%"=="integration" goto run_integration
if /i "%MODE%"=="endpoints" goto run_endpoints
if /i "%MODE%"=="movies" goto run_movies
if /i "%MODE%"=="streaming" goto run_streaming
if /i "%MODE%"=="single" goto run_single
if /i "%MODE%"=="help" goto show_help
if /i "%MODE%"=="-h" goto show_help
if /i "%MODE%"=="--help" goto show_help

echo [ERROR] Mode inconnu: %MODE%
goto show_help

:run_fast
echo.
echo ===============================================================
echo Execution TESTS RAPIDES (sans slow)
echo ===============================================================
echo.
pytest tests/ -m "not slow" -v --tb=short
exit /b %ERRORLEVEL%

:run_all
echo.
echo ===============================================================
echo Execution TOUS LES TESTS
echo ===============================================================
echo.
pytest tests/ -v --tb=short
exit /b %ERRORLEVEL%

:run_coverage
echo.
echo ===============================================================
echo Execution avec COUVERTURE CODE
echo ===============================================================
echo.
pytest tests/ ^
    --cov=app ^
    --cov-report=html ^
    --cov-report=term-missing ^
    -v
echo.
echo [OK] Rapport HTML genere: htmlcov/index.html
echo.
exit /b %ERRORLEVEL%

:run_debug
echo.
echo ===============================================================
echo Mode DEBOGAGE (verbose + logs)
echo ===============================================================
echo.
pytest tests/ -vv -s --tb=long --log-cli-level=DEBUG
exit /b %ERRORLEVEL%

:run_integration
echo.
echo ===============================================================
echo Execution TESTS D'INTEGRATION
echo ===============================================================
echo.
pytest tests/test_integration.py -v --tb=short
exit /b %ERRORLEVEL%

:run_endpoints
echo.
echo ===============================================================
echo Execution TESTS ENDPOINTS
echo ===============================================================
echo.
pytest tests/test_api_endpoints.py -v --tb=short
exit /b %ERRORLEVEL%

:run_movies
echo.
echo ===============================================================
echo Execution TESTS FILMS/SERIES
echo ===============================================================
echo.
pytest tests/test_api_movies.py -v --tb=short
exit /b %ERRORLEVEL%

:run_streaming
echo.
echo ===============================================================
echo Execution TESTS STREAMING
echo ===============================================================
echo.
pytest tests/test_api_streaming.py -v --tb=short
exit /b %ERRORLEVEL%

:run_single
if "%2"=="" (
    echo [ERROR] Specifier le test a executer
    echo.
    echo Exemple: test-runner.bat single tests/test_api_endpoints.py::TestGetServers
    echo.
    exit /b 1
)
echo.
echo ===============================================================
echo Execution TEST UNIQUE
echo ===============================================================
echo.
pytest %2 -vv --tb=short
exit /b %ERRORLEVEL%

:show_help
echo.
echo PlexHub Test Runner
echo.
echo Usage: test-runner.bat [option]
echo.
echo Options:
echo     (defaut)       Tous les tests rapides (sans slow)
echo     all            Tous les tests (y compris slow)
echo     coverage       Avec rapport de couverture HTML
echo     debug          Mode debogage (verbose + logs)
echo     integration    Seulement tests d'integration
echo     endpoints      Seulement tests endpoints REST
echo     movies         Seulement tests films/series
echo     streaming      Seulement tests streaming
echo     single ^<test^>  Un test specifique
echo     help           Afficher cette aide
echo.
echo Exemples:
echo     test-runner.bat
echo     test-runner.bat coverage
echo     test-runner.bat single tests/test_api_endpoints.py::TestGetServers::test_get_servers_success
echo.
exit /b 0
