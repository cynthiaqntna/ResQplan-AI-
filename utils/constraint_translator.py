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
    """Extrae variables clave y genera las variables de decisión en formato Gurobi."""

    client = get_openai_client()

    prompt = (
        "A partir de la siguiente descripción de un problema de planificación de turnos, "
        "extrae las variables clave necesarias para definir el modelo matemático. "
        "Identifica correctamente la entidad principal del problema (por ejemplo, retenes en un caso de emergencias, "
        "o asignaturas en un caso de horarios escolares). "
        "Asegúrate de que las variables de decisión usen esa entidad como primera clave en la estructura del diccionario. "
        "Además, genera las variables de decisión en código Python usando Gurobi con el siguiente formato: "
        "self.x = {(entidad, d, t): self.model.addVar(...)} donde 'entidad' siempre debe ser el elemento principal del problema. "
        "Devuelve la respuesta ÚNICAMENTE en formato JSON sin explicaciones. "
        "Ejemplo de salida:\n"
        '{\n  "variables": {\n    "num_retenes": 22,\n    "dias": 7,\n    "num_turnos": 2,\n    "horarios": ["08:00-20:00", "20:00-08:00"]\n  },\n'
        '  "decision_variables": "self.d = {(r, d, t): self.model.addVar(vtype=GRB.BINARY, name=f\'d_{r}_{d}_{t}\') for r in range(self.num_retenes) for d in range(self.dias) for t in range(self.num_turnos)}"\n}'
        f"\n\nDescripción del problema: {context}"
    )

    try:
        response = client.chat.completions.create(
            model="o3-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return json.loads(response.choices[0].message.content.strip())

    except json.JSONDecodeError as err:
        raise RuntimeError(f"❌ Error al analizar la respuesta JSON: {err}")
    except Exception as e:
        raise RuntimeError(f"❌ Error al extraer variables: {e}")


def translate_constraint_to_code(nl_constraint: str, variables: dict) -> str:
    """Traduce una restricción en lenguaje natural a código Python válido para Gurobi."""

    client = get_openai_client()

    prompt = (
        "Eres un experto en optimización con Gurobi. "
        "Convierte la siguiente restricción en código Python usando model.addConstr(...). "
        "Si la restricción tiene una condición del tipo lb <= expr <= ub, "
        "descomponla en dos restricciones separadas para que Gurobi las acepte correctamente: "
        "model.addConstr(expr >= lb) y model.addConstr(expr <= ub). "
        "Incluye un argumento 'name=' en cada restricción, generando un nombre identificativo y descriptivo "
        "a partir de la restricción original (en inglés o snake_case si es largo). "
        "NO agregues explicaciones, comentarios ni bloques de código adicionales. "
        f"Las variables disponibles en este problema son:\n{json.dumps(variables, indent=2)}\n\n"
        "Usa ÚNICAMENTE estas variables en tu respuesta.\n"
        "Recuerda que las variables de decisión se han definido utilizando el alias 'd_vars' y se han creado con la notación d_vars[(r, d, t)], donde:\n"
        "  - el primer índice (r) corresponde a la primera dimensión y toma valores de 0 hasta (cantidad - 1),\n"
        "  - el segundo índice (d) corresponde a la segunda dimensión y toma valores de 0 hasta (cantidad - 1),\n"
        "  - el tercer índice (t) corresponde a la tercera dimensión y toma valores de 0 hasta (cantidad - 1).\n"
        "Genera el código usando exactamente ese orden de índices, sin invertirlos ni sumar 1 a los rangos.\n"
        "No uses gp.quicksum solo quicksum.\n"
        "Devuelve SOLO el código válido sin formato Markdown ni explicaciones.\n\n"
        f"Restricción: {nl_constraint}"
    )

    for attempt in range(config.MAX_ATTEMPTS):
        try:
            response = client.chat.completions.create(
                model="o3-mini",
                messages=[{"role": "user", "content": prompt}]
            )
            code = response.choices[0].message.content.strip()

            # Verificar sintaxis antes de devolverlo
            compile(code, "<string>", "exec")
            return code

        except Exception as e:
            print(f"⚠️ Intento {attempt + 1} fallido: {e}. Reintentando...")
            time.sleep(1)

    raise RuntimeError("❌ No se pudo traducir la restricción después de varios intentos.")