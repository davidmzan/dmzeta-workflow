#!/bin/bash
# Pasa las pruebas de regresión. Doble clic o: ./run_tests.command
cd "$(dirname "$0")"
python3 -B -W ignore -m unittest discover -s tests 2>&1 | grep -E "^(Ran|OK|FAILED|ERROR|FAIL)|Error|assert" 
exit ${PIPESTATUS[0]}
