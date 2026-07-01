# LDA Smart Analyzer v3

Aplicación Streamlit + LangGraph para levantamiento LDA real desde formularios, con base SQLite local, cálculos de volumetría, validación de reglas LDA, enriquecimiento de campos para el consultor y análisis opcional con OpenAI.

## Qué mejora esta versión

- El consultor no carga Excel por entrevista. El DOP se importa una sola vez.
- La app ya trae entrevistas demo con volumetría realista para ver cálculos y análisis desde el primer arranque.
- Permite pegar la `OPENAI_API_KEY` en la barra lateral y activar IA externa.
- La IA puede enriquecer actividades desde el DOP con:
  - proceso/subproceso,
  - tipo de actividad,
  - pregunta de validación,
  - evidencia esperada,
  - herramienta/sistema,
  - entregable,
  - indicador/KPI,
  - criticidad,
  - automatizable,
  - riesgo,
  - dependencia,
  - oportunidad `A`, `R` o `-`.
- El formulario calcula en vivo:
  - Vol Mes,
  - Min Mes,
  - Hrs Mes,
  - Min Día,
  - % jornada,
  - cumplimiento ponderado,
  - riesgo,
  - ahorro potencial,
  - errores LDA.
- El análisis compara carga real contra tiempo estándar diario y genera conclusión rápida.
- Exporta Excel enriquecido con resumen, tabla LDA y resumen por procesos.

## Estructura

```text
lda_smart_analyzer_v3/
  app.py
  requirements.txt
  .env.example
  data/
    samples/
      DOP_Envio_Andres.xlsx
      Formato_LDA_ORIGINAL.xlsx
  exports/
  src/
    ai_graph.py
    ai_service.py
    db.py
    dop_service.py
    lda_rules.py
    reporting.py
```

## Instalación en Mac

```bash
cd lda_smart_analyzer_v3
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.port 8501
```

## Instalación en Windows PowerShell

```powershell
cd lda_smart_analyzer_v3
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py --server.port 8501
```

Abre:

```text
http://localhost:8501
```

## Cómo activar OpenAI

Opción 1: desde la app

1. Abre la barra lateral.
2. Marca **Usar OpenAI para generar y analizar**.
3. Pega tu `OPENAI_API_KEY`.
4. Selecciona modelo, por ejemplo `gpt-4o-mini`.
5. Presiona **Guardar configuración IA**.

Opción 2: archivo `.env`

```bash
cp .env.example .env
```

Edita `.env`:

```text
OPENAI_API_KEY=tu_api_key
OPENAI_MODEL=gpt-4o-mini
USE_OPENAI=true
```

## Flujo de uso

1. **Base / Super Usuario**: importa DOP una sola vez o usa el ejemplo incluido.
2. Activa IA si quieres regenerar actividades enriquecidas desde el DOP.
3. **Formulario Consultor**: selecciona cargo, consultor y entrevistado.
4. Completa o corrige actividades, frecuencia, semanas, tiempo, cumplimiento y evidencia.
5. Revisa el **cálculo en vivo** antes de guardar.
6. Presiona **Guardar entrevista y analizar**.
7. Revisa la conclusión en **Análisis**.
8. Exporta a Excel desde **Exportar**.

## Fórmulas usadas

```text
Vol Mes = Diario*22 + Semanal*4.3 + Quincenal*2 + Mensual + Anual/12
Min Mes = Tiempo x Unidad * Vol Mes
Hrs Mes = Min Mes / 60
Min Día = Min Mes / 22
% Jornada = Min Día / Tiempo estándar diario
```

## Reglas LDA básicas

- Debe marcarse al menos una semana.
- Debe seleccionarse una sola frecuencia.
- Debe indicarse tiempo por unidad mayor a cero.
- Actividad diaria/semanal debe marcar las 4 semanas.
- Actividad quincenal debe marcar exactamente 2 semanas.
- Actividad mensual debe marcar exactamente 1 semana.
- Si se declara cumplimiento, debe haber evidencia o forma de verificación.

