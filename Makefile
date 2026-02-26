.PHONY: install dev prod test lint clean

# ─── Installation ─────────────────────────────────────────────────────────────
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt pytest pytest-asyncio

# ─── Développement local ──────────────────────────────────────────────────────
dev:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug

# ─── Production (VPS) ────────────────────────────────────────────────────────
prod:
	gunicorn -c gunicorn.conf.py app.main:app

# ─── Tests ────────────────────────────────────────────────────────────────────
test:
	pytest tests/ -v --tb=short

test-config:
	pytest tests/test_config.py -v

# ─── Lint ─────────────────────────────────────────────────────────────────────
lint:
	python -m py_compile app/*.py && echo "Syntax OK"

# ─── Utilitaires ──────────────────────────────────────────────────────────────
gen-secret:
	python -c "import secrets; print(secrets.token_hex(32))"

# Vérifier que l'API répond
health:
	curl -s http://localhost:8000/health | python -m json.tool

# Tester un job complet (nécessite .env rempli)
test-generate:
	curl -s -X POST http://localhost:8000/generate \
		-H "Authorization: Bearer $$(grep API_SECRET_KEY .env | cut -d= -f2)" \
		-H "Content-Type: application/json" \
		-d '{"sheets_row": {"row_id": "row_test_1", "script": "Script de test pour vérifier le pipeline complet. Ceci est une démonstration.", "format": "vertical", "strategy": "A", "duration": 90, "voice_id": "test_voice_id", "cta": "Contactez-nous"}}' \
		| python -m json.tool

# ─── Nettoyage ────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	find . -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null; true
