import json

def append_markdown_cell(notebook_path, content):
    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            nb = json.load(f)
        
        cell = {
            "cell_type": "markdown",
            "metadata": {},
            "source": [line + "\n" for line in content.split("\n")]
        }
        
        nb.get('cells', []).append(cell)
        
        with open(notebook_path, 'w', encoding='utf-8') as f:
            json.dump(nb, f, indent=1, ensure_ascii=False)
        print(f"Documentado en {notebook_path}")
    except Exception as e:
        print(f"Error procesando {notebook_path}: {e}")

# 1. Documentar ML en HIPOTECA_PERSONALIZADA.ipynb
ml_doc = """## Integración de Modelos de Machine Learning (ML)
Para predecir el comportamiento del Spread Hipotecario (`Spread_Hipotecas`) y simular escenarios futuros (como el periodo 2027-2030), se ha entrenado un modelo **Gradient Boosting Regressor** de `scikit-learn` en el entorno web.

Las características principales del enfoque son:
1. **Evitar Data Leakage**: El modelo se entrena en tiempo real con datos estrictamente anteriores al año solicitado.
2. **Características Predictivas**: Se utilizan las variables macroeconómicas clave (`Euribor`, `IPC`, `Tasa_Paro`, `PIB_pc`, `tasa_ahorro`, `Precio_m2`).
3. **Escenarios a Futuro (2027-2030)**: Para esta simulación a ciegas, se usan los datos agregados más recientes disponibles en el histórico como semilla, permitiendo al Gradient Boosting usar todo el conjunto histórico para predecir.
4. **Resultados Duales**: Se ofrece al cliente el "Tipo Básico" (según reglas heurísticas) y un "Tipo Óptimo ML" (basado en la recomendación de regresión y el DTI del cliente).
"""
append_markdown_cell("HIPOTECA_PERSONALIZADA.ipynb", ml_doc)

# 2. Documentar Noa y pasos web en pasos_web.ipynb
web_doc = """## Desarrollo Final: Asistente Noa y Selector de Fechas (2027-2030)
En los últimos pasos del desarrollo de la plataforma web, se integraron los siguientes elementos avanzados:

1. **Noa - Asistente Hipotecaria Inteligente**:
   - Integrada usando la API de Gemini (`google.generativeai`).
   - Existen dos modos: la versión cliente (enfocada en resolver dudas y explicar el tipo obtenido) y la versión "Strategic" oculta para gestores, enfocada en la argumentación de ventas y análisis de DTI.
   - El sistema le pasa el contexto local íntegro (ingresos, precio vivienda, tipo ML, variables macro) en un prompt estructurado cada vez que se envía un chat.

2. **Simulaciones a Futuro (2027-2030)**:
   - Se modificó dinámicamente el selector de año del frontend y los endpoints del backend (`/api/data`, `/api/hipoteca-context`, `/api/hipoteca-recomendacion`) para admitir la franja 2027-2030.
   - Puesto que el Dataset origen está limitado hasta 2024/2025, el servidor inyecta los últimos valores conocidos de inflación e interés y delega el esfuerzo al modelo ML (entrenado con toda la serie histórica).

3. **Arquitectura y Estabilidad**:
   - Para solventar *deadlocks* nativos de macOS con las librerías C subyacentes de Scikit-Learn y Flask, se migró `app.run` a un solo hilo (`threaded=False`) y se movieron las importaciones analíticas al scope global.
"""
append_markdown_cell("pasos_web.ipynb", web_doc)
