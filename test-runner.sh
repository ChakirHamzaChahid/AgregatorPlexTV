#!/bin/bash
# test-runner.sh - Script de lancement rapide des tests
# 
# Usage:
#   bash test-runner.sh              # Tous les tests (rapides)
#   bash test-runner.sh all          # Tous les tests (y compris slow)
#   bash test-runner.sh coverage     # Avec rapport de couverture
#   bash test-runner.sh debug        # Mode débogage verbose
#   bash test-runner.sh integration  # Seulement tests intégration
#

set -e

# Couleurs pour le output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Fonctions d'affichage
print_header() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Vérifier pytest
check_pytest() {
    if ! command -v pytest &> /dev/null; then
        print_error "pytest non installé!"
        echo "Installation: pip install -r requirements-test.txt"
        exit 1
    fi
    print_success "pytest trouvé"
}

# Mode par défaut: tests rapides
run_fast() {
    print_header "Exécution TESTS RAPIDES (sans slow)"
    pytest tests/ -m "not slow" -v --tb=short
}

# Mode all: tous les tests
run_all() {
    print_header "Exécution TOUS LES TESTS"
    pytest tests/ -v --tb=short
}

# Mode coverage: rapport de couverture
run_coverage() {
    print_header "Exécution avec COUVERTURE CODE"
    pytest tests/ \
        --cov=app \
        --cov-report=html \
        --cov-report=term-missing \
        -v
    
    print_success "Rapport HTML généré: htmlcov/index.html"
}

# Mode debug: verbose + logs
run_debug() {
    print_header "Mode DÉBOGAGE (verbose + logs)"
    pytest tests/ -vv -s --tb=long --log-cli-level=DEBUG
}

# Mode integration: seulement tests d'intégration
run_integration() {
    print_header "Exécution TESTS D'INTÉGRATION"
    pytest tests/test_integration.py -v --tb=short
}

# Mode endpoints: seulement endpoints REST
run_endpoints() {
    print_header "Exécution TESTS ENDPOINTS"
    pytest tests/test_api_endpoints.py -v --tb=short
}

# Mode movies: seulement tests films/séries
run_movies() {
    print_header "Exécution TESTS FILMS/SÉRIES"
    pytest tests/test_api_movies.py -v --tb=short
}

# Mode streaming: seulement tests streaming
run_streaming() {
    print_header "Exécution TESTS STREAMING"
    pytest tests/test_api_streaming.py -v --tb=short
}

# Mode rapide individual test
run_single_test() {
    print_header "Exécution TEST UNIQUE"
    pytest "$1" -vv --tb=short
}

# Affichage d'aide
show_help() {
    cat << EOF
${BLUE}PlexHub Test Runner${NC}

Usage: bash test-runner.sh [option]

Options:
    (defaut)       Tous les tests rapides (sans slow)
    all            Tous les tests (y compris slow)
    coverage       Avec rapport de couverture HTML
    debug          Mode débogage (verbose + logs)
    integration    Seulement tests d'intégration
    endpoints      Seulement tests endpoints REST
    movies         Seulement tests films/séries
    streaming      Seulement tests streaming
    single <test>  Un test spécifique
    help           Afficher cette aide

Exemples:
    bash test-runner.sh
    bash test-runner.sh coverage
    bash test-runner.sh single tests/test_api_endpoints.py::TestGetServers::test_get_servers_success

EOF
}

# Main
main() {
    check_pytest
    
    case "${1:-}" in
        "all")
            run_all
            ;;
        "coverage")
            run_coverage
            ;;
        "debug")
            run_debug
            ;;
        "integration")
            run_integration
            ;;
        "endpoints")
            run_endpoints
            ;;
        "movies")
            run_movies
            ;;
        "streaming")
            run_streaming
            ;;
        "single")
            if [ -z "$2" ]; then
                print_error "Spécifier le test à exécuter"
                echo "Exemple: bash test-runner.sh single tests/test_api_endpoints.py::TestGetServers"
                exit 1
            fi
            run_single_test "$2"
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        "")
            run_fast
            ;;
        *)
            print_error "Option inconnue: $1"
            show_help
            exit 1
            ;;
    esac
}

# Lancer
main "$@"
