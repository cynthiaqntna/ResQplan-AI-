import os
import json
import time
import config
from openai import OpenAI


def get_openai_client():
    """Inicializa y devuelve un cliente OpenAI."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("⚠️ La variable de entorno OPENAI_API_KEY no está configurada.")
    return OpenAI(api_key=api_key)


def extract_variables_from_context(context: str) -> dict:
    """
    A partir de un texto de gestión de turnos (colegio, hospital, emergencias, etc.) que incluye:
      - Descripción del problema (días, franjas horarias, objetivos).
      - Catálogo de recursos y roles (retenes, ambulancias, médicos, enfermeros, conductores, aulas, profesores, pacientes, etc.).
    Extrae y devuelve un JSON con cuatro campos:
      1) "variables": {...}
      2) "resources": {...}
      3) "decision_variables": <str>
      4) "detected_constraints": [<str>, ...]  ← **NUEVO**: restricciones detectadas en el texto de entrada
    ***Importante***: Devuelve **solo** el JSON resultado, sin explicaciones, comentarios o formato Markdown.
    """
    client = get_openai_client()

    prompt = (
        "Eres un ingeniero experto en modelos de programación lineal con Gurobi.\n"
        "Recibirás un texto que describe un problema de planificación de turnos o asignaciones"
        "(colegio, hospital, emergencias, etc.). El texto incluye:\n"
        " • Horizonte temporal (número de días, número de franjas y horarios).\n"
        " • Listas de entidades a asignar (retenes, profesores, médicos, ambulancias, cursos, asignaturas, etc.).\n"
        " • Cantidades de recursos disponibles.\n\n"

        "Debes construir un ÚNICO objeto JSON con TRES claves obligatorias:\n" 
        "1) \"variables\"  ⇒ diccionario que contenga SIEMPRE:\n"
        "      - \"dias\"      : <int>,\n"
        "      - \"franjas\"   : <int>,\n"
        "      - \"horarios\"  : [<str>, ...]\n"
        "   además de una lista por cada entidad detectada, con nombre "
        "      'lista_<entidad_plural>' (p. ej. 'lista_retenes', 'lista_medicos', 'lista_cursos', 'lista_asignaturas').\n"
        "2) \"resources\"  ⇒ diccionario con la cantidad disponible de cada recurso "
        "(p. ej. {\"ambulancias\": 3, \"medicos\": 5, \"conductores\": 6}).\n"
        "3) \"decision_variables\"  ⇒ bloque de código Python **válido**, con una instrucción self.x_<nombre> por cada tipo de asignación detectada."
        " Para asignaciones individuales (enti es decir, entidades sin relación), declara una variable así:\n"
        "      self.x_recurso = { (r, d, f): model.addVar(vtype=GRB.BINARY, name=f\"x_{r}_{d}_{f}\")"
        "                            for r in variables['lista_recurso']"
        "                            for d in range(variables['dias'])"
        "                            for f in range(variables['franjas']) }\n"
        "Para asignaciones que involucren tres entidades (por ejemplo, profesor, curso y asignatura), hazlo así:\n"
        "    self.x_profesor_curso_asignatura = {\n"
        "        (p, c, a, d, f): model.addVar(vtype=GRB.BINARY, name=f\"x_{p}_{c}_{a}_{d}_{f}\")\n"
        "        for p in variables['lista_profesores']\n"
        "        for c in variables['lista_cursos']\n"
        "        for a in variables['lista_asignaturas']\n"
        "        for d in range(variables['dias'])\n"
        "        for f in range(variables['franjas'])\n"
        "    }"
        "   • No utilices bucles 'for:' sueltos fuera de la comprensión.\n"
        "   • Usa directamente 'model.addVar' y 'GRB.BINARY' (no 'self.model.GRB').\n"
        "   • El resultado de la comprensión debe ser un gurobipy.tupledict.\n"
        "   • Asegúrate de escribir saltos de línea REALES, no '\\n' escapados.\n\n"
        "En el caso que detectes alguna restricción en el contexto (Oraciones meramente descriptivas (horarios, cantidades, desplazamientos) no se incluirán.),añade la siguiente clave (SOLO EN EL CASO QUE LO DETECTES):"
       "4) \"detected_constraints\"  ⇒ lista de cadenas, **sin** convertirlas en código, " 
        "   que contenga todas las oraciones del texto de entrada que parezcan "
        "   restricciones en lenguaje natural.\n\n"
        "Si no se detecta ninguna restricción válida, devuelve 'detected_constraints': []` o no incluyas esa clave."
        "⚠️ IMPORTANTE: Si el texto no describe un problema de turnos, responde únicamente con:\n"
        "{ \"error\": \"El texto no describe un problema de turnos válido.\" }\n\n"
        "Devuelve **solo** ese JSON, sin comentarios ni Markdown.\n\n"
        f"=== TEXTO DE ENTRADA ===\n{context}\n======================="
    )

    try:
        resp = client.chat.completions.create(
            model="o3-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        content = resp.choices[0].message.content.strip()
        data = json.loads(content)

        if "error" in data:
            return {"error": data["error"]}

        # Inicializar lista de restricciones detectadas si no viene
        if 'detected_constraints' not in data:
            data['detected_constraints'] = []

        # Validaciones básicas
        if not all(k in data for k in ('variables', 'resources', 'decision_variables', 'detected_constraints')):
            return {"error": "El JSON de salida no tiene las claves requeridas."}
        vars_dict = data['variables']
        for key in ('dias', 'franjas', 'horarios'):
            if key not in vars_dict:
                return {"error": f"Falta la variable obligatoria '{key}' en 'variables'."}

        return data

    except json.JSONDecodeError as e:
        return {"error": f"El JSON devuelto no es válido: {e}"}
    except Exception as e:
        return {"error": f"Error durante la extracción de datos: {e}"}



def translate_constraint_to_code(nl_constraint: str, specs: dict) -> str:
    """
    Traduce una restricción en lenguaje natural a código Python Gurobi:
      - specs es el JSON producido por extract_variables_from_context,
        e incluye tanto 'variables' como 'resources'.
      - Usa 'model.addConstr(...)'. Si la forma es 'lb <= expr <= ub', divides en dos llamadas.
      - Usa 'quicksum' para sumatorios.
      - Nombra cada restricción con 'name=' en snake_case derivado de la propia restricción.
      - Refierete siempre a las variables de decisión usando 'x[(...)]' en el orden de índices definido.
    Devuelve sólo el bloque de código ejecutable, sin explicaciones ni formato adicional.
    """
    client = get_openai_client()
    prompt = (
        "Eres un experto en optimización con Gurobi.\n"
        "Tienes disponible un JSON 'specs' con las claves 'variables' y 'resources':\n"
        f"{json.dumps(specs, indent=2)}\n"
        "Ten en cuenta que el JSON se estrcutura de esta manera:\n"
        "1) \"variables\"  ⇒ diccionario que contenga SIEMPRE:\n"
        "      - \"dias\"      : <int>,\n"
        "      - \"franjas\"   : <int>,\n"
        "      - \"horarios\"  : [<str>, ...]\n"
        "   además de una lista por cada entidad detectada, con nombre "
        "      'lista_<entidad_plural>' (p. ej. 'lista_retenes', 'lista_medicos').\n"
        "2) \"resources\"  ⇒ diccionario con la cantidad disponible de cada recurso "
        "(p. ej. {\"ambulancias\": 3, \"medicos\": 5, \"conductores\": 6}).\n"
        "3) \"decision_variables\"  ⇒ bloque de código Python **válido**, con una instrucción x_<nombre_recurso> por cada tipo de entidad (retenes, ambulancias, profesores, etc.)."
        f"Genera el código Python válido que implemente la siguiente restricción:\n{nl_constraint}\n"
        "Requisitos:\n"
        "- Usa model.addConstr().\n"
        "- Si lb <= expr <= ub, crea dos restricciones separadas.\n"
        "- Usa quicksum para sumas.\n"
        "- Nombra cada restricción con name=''.\n"
        "- Accede a las variables a través de 'specs[\"variables\"]', por ejemplo: specs['variables']['dias'], y usa los nombres adecuados como 'x_retenes' o 'x_conductores'.\n"
        "- Refierete a las variables de decisión usando los nombres separados por tipo, como 'x_retenes[(r, d, f)]', 'x_conductores[(r, d, f)]', etc., según el tipo de recurso correspondiente.\n"
        "\n\n⚠️ IMPORTANTE: Si la restricción en lenguaje natural no se corresponde con ninguna variable o recurso "
       "del problema, responde SÓLO con:\n"
       '{ "error": "La restricción no aplica al contexto proporcionado." }\n'
       "Sin explicaciones ni Markdown, sólo ese JSON."
        "Devuelve SOLO el código, sin explicaciones ni Markdown."
    )
    for attempt in range(config.MAX_ATTEMPTS):
        try:
            resp = client.chat.completions.create(
                model="o3-mini",
                messages=[{"role": "user", "content": prompt}]
            )
            content = resp.choices[0].message.content.strip()

            # Si es JSON de error, lo devolvemos como dict
            if content.startswith('{') and '"error"' in content:
                return json.loads(content)

            # Si no, asumimos que es código
            compile(content, '<string>', 'exec')  # valida el código
            return content

        except Exception as e:
            print(f"⚠️ Error traducción intento {attempt + 1}: {e}")
            time.sleep(1)

    raise RuntimeError("❌ No se pudo traducir la restricción tras múltiples intentos.")