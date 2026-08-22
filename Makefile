# El entorno local del lider (Windows) no tiene make. Los comandos son
# one-liners a proposito: si no tienes make, copia la linea de la receta.
.PHONY: help ingest build graph test report load up down lint
help:
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

ingest:   ## Descarga el universo de obra publica del SECOP II (~4 min)
	python pipeline/ingest.py

build:    ## Warehouse + publica data/exports/base.parquet (~20 s)
	python pipeline/build.py

graph:    ## Solo el grafo (pasos 04-09), sin recalcular el nucleo
	python pipeline/build.py --steps 04 05 --no-export
	python pipeline/grafo.py

all:      ## Todos los pasos SQL en orden
	python pipeline/build.py --all

valores:  ## Tipo de obra + la cifra en pesos (pasos 10-11)
	python pipeline/build.py --steps 10 11 --no-export

abiertos: ## Snapshot de hoy de licitaciones abiertas (~1 min)
	python pipeline/ingest_abiertos.py

alertas:  ## Banderas pre-adjudicacion (requiere build + abiertos)
	python pipeline/alertas.py

web:      ## Exporta JSON y sirve el tablero en http://localhost:8080
	python pipeline/export_web.py
	cd web && python -m http.server 8080

report:   ## Rankings por consola + CSVs en out/
	python pipeline/report.py

test:     ## Puertas de calidad de datos (fallan el PR)
	python -m pytest tests/ -v

lint:
	ruff check pipeline api tests

load:     ## Carga el warehouse a Postgres para el API
	python pipeline/load_postgres.py

up:
	docker compose up --build

down:
	docker compose down
