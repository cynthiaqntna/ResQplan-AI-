# tests/test_constraint_translator.py

import pytest
import json

import utils.constraint_translator as ct

class DummyChoice:
    def __init__(self, content):
        self.message = type("msg", (), {"content": content})

class DummyResponse:
    def __init__(self, content):
        self.choices = [DummyChoice(content)]

class DummyChatCompletions:
    def __init__(self, return_content):
        self._content = return_content

    def create(self, model, messages):
        return DummyResponse(self._content)

class DummyOpenAIClient:
    def __init__(self, return_content):
        self.chat = type("chat", (), {"completions": DummyChatCompletions(return_content)})

@pytest.fixture(autouse=True)
def patch_openai_client(monkeypatch):
    """
    Fixture que parchea get_openai_client para devolver un cliente dummy.
    Cada test asignará ct._dummy_content con la respuesta que quiera simular.
    """
    def fake_get_client():
        return DummyOpenAIClient(ct._dummy_content)
    monkeypatch.setattr(ct, "get_openai_client", fake_get_client)
    yield
    if hasattr(ct, "_dummy_content"):
        delattr(ct, "_dummy_content")


def test_extract_variables_success():
    # Preparamos un JSON de respuesta válido para extract_variables_from_context
    fake_json = {
        "variables": {
            "num_asignaturas": 5,
            "dias": 5,
            "franjas": 2,
            "horarios": ["08:00-09:00", "09:00-10:00"],
            "lista_asignaturas": ["Algebra", "Fisica", "Quimica", "Biologia", "Literatura"],
            "lista_profesores": ["ProfA", "ProfB"]
        },
        "resources": {
            "profesores": 2,
            "aulas": 3
        },
        "decision_variables": (
            "self.x_asignatura = { (a, d, f): model.addVar(vtype=GRB.BINARY, name=f\"x_{a}_{d}_{f}\") "
            "for a in variables['lista_asignaturas'] for d in range(variables['dias']) for f in range(variables['franjas']) }"
        ),
        "detected_constraints": []
    }
    ct._dummy_content = json.dumps(fake_json)

    context = (
        "Se quiere planificar el horario para 5 asignaturas: Álgebra, Física, Química, "
        "Biología y Literatura. Cada asignatura debe impartir 4 horas semanales, "
        "divididas en 2 horas de teoría y 2 horas de práctica. "
        "El horario se compone de 5 días, cada uno con 2 franjas horarias: 08:00-09:00, 09:00-10:00."
    )
    variables = ct.extract_variables_from_context(context)

    # Verificamos que la salida coincida con el JSON fake
    assert "variables" in variables
    v = variables["variables"]
    assert v["num_asignaturas"] == 5
    assert v["dias"] == 5
    assert v["franjas"] == 2
    assert v["horarios"] == ["08:00-09:00", "09:00-10:00"]
    assert "lista_asignaturas" in v
    assert variables["resources"]["profesores"] == 2
    assert "decision_variables" in variables
    # El código debe compilar
    try:
        compile(variables["decision_variables"], "<string>", "exec")
    except Exception as e:
        pytest.fail(f"El bloque de decision_variables no compila: {e}")


def test_extract_variables_error():
    # Simulamos que la respuesta de ChatGPT es un JSON de error
    error_json = {"error": "El texto no describe un problema de turnos válido."}
    ct._dummy_content = json.dumps(error_json)

    context = "Este texto no tiene nada que ver con horarios."
    result = ct.extract_variables_from_context(context)

    assert isinstance(result, dict)
    assert "error" in result
    assert result["error"] == "El texto no describe un problema de turnos válido."


def test_translate_constraint_success():
    # Preparamos un fragmento de código Python válido para translate_constraint_to_code
    fake_code = (
        "for a in variables['lista_asignaturas']:\n"
        "    for d in range(variables['dias']):\n"
        "        for f in range(variables['franjas']):\n"
        "            model.addConstr(x_asignatura[(a,d,f)] <= 1, name=f\"max_unidad_{a}_{d}_{f}\")"
    )
    ct._dummy_content = fake_code

    specs = {
        "variables": {
            "lista_asignaturas": ["Algebra", "Fisica"],
            "dias": 5,
            "franjas": 6
        },
        "resources": {}
    }
    nl_constraint = "cada asignatura no puede impartirse más de una vez en la misma franja del mismo día"
    codigo = ct.translate_constraint_to_code(nl_constraint, specs)

    assert isinstance(codigo, str)
    assert "for" in codigo  # Debe contener un bucle for
    # Debe compilarse sin errores
    try:
        compile(codigo, "<string>", "exec")
    except Exception as e:
        pytest.fail(f"El código generado por translate_constraint_to_code no compila: {e}")


def test_translate_constraint_error():
    # Simulamos que ChatGPT retorna un JSON con clave "error"
    error_json = {"error": "La restricción no aplica al contexto proporcionado."}
    ct._dummy_content = json.dumps(error_json)

    specs = {
        "variables": {
            "lista_asignaturas": ["Algebra"],
            "dias": 1,
            "franjas": 1
        },
        "resources": {}
    }
    nl_constraint = "restricción irrelevante para este modelo"
    resultado = ct.translate_constraint_to_code(nl_constraint, specs)

    assert isinstance(resultado, dict)
    assert "error" in resultado
    assert resultado["error"] == "La restricción no aplica al contexto proporcionado."


def test_extract_variables_minimal_context():
    # Respuesta mínima pero válida
    fake_json = {
        "variables": {
            "num_asignaturas": 1,
            "dias": 1,
            "franjas": 1,
            "horarios": ["08:00-09:00"],
            "lista_asignaturas": ["A1"]
        },
        "resources": {},
        "decision_variables": (
            "self.x_asignatura = { (a, d, f): model.addVar(vtype=GRB.BINARY, name=f\"x_{a}_{d}_{f}\") "
            "for a in variables['lista_asignaturas'] for d in range(variables['dias']) for f in range(variables['franjas']) }"
        ),
        "detected_constraints": []
    }
    ct._dummy_content = json.dumps(fake_json)

    context = "Planificar horario para 1 asignatura en 1 día, 1 franja: 08:00-09:00."
    variables = ct.extract_variables_from_context(context)

    v = variables["variables"]
    assert v["num_asignaturas"] == 1
    assert v["dias"] == 1
    assert v["franjas"] == 1
    assert v["horarios"] == ["08:00-09:00"]
    # decision_variables debe existir y compilar
    dv_code = variables["decision_variables"]
    assert dv_code
    try:
        compile(dv_code, "<string>", "exec")
    except Exception as e:
        pytest.fail(f"El código en 'decision_variables' no compila: {e}")


def test_decision_variables_compilation():
    # Verificamos que 'decision_variables' compile correctamente
    fake_json = {
        "variables": {
            "lista_asignaturas": ["A1", "A2", "A3"],
            "dias": 2,
            "franjas": 4,
            "horarios": ["08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00"]
        },
        "resources": {},
        "decision_variables": (
            "self.x_asignatura = { (a, d, f): model.addVar(vtype=GRB.BINARY, name=f\"x_{a}_{d}_{f}\") "
            "for a in variables['lista_asignaturas'] for d in range(variables['dias']) for f in range(variables['franjas']) }"
        ),
        "detected_constraints": []
    }
    ct._dummy_content = json.dumps(fake_json)

    context = (
        "Planificar el horario para 3 asignaturas en 2 días con 4 franjas: "
        "08:00-09:00, 09:00-10:00, 10:00-11:00, 11:00-12:00. "
        "Cada asignatura impartirá 2 horas de teoría y 2 horas de práctica."
    )
    variables = ct.extract_variables_from_context(context)
    decision_code = variables.get("decision_variables")
    assert decision_code, "No se encontró código en 'decision_variables'."
    try:
        compile(decision_code, "<string>", "exec")
    except Exception as e:
        pytest.fail(f"El código en 'decision_variables' no compila: {e}")
