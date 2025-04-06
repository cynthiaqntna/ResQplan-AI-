import pytest
from utils.constraint_translator import extract_variables_from_context, translate_constraint_to_code


def test_extract_variables():
    context = (
        "Se quiere planificar el horario para 5 asignaturas: Álgebra, Física, Química, Biología y Literatura. "
        "Cada asignatura debe impartir 4 horas semanales, divididas en 2 horas de teoría y 2 horas de práctica. "
        "El horario se compone de 5 días, cada uno con 6 franjas horarias: 08:00–09:00, 09:00–10:00, 10:00–11:00, "
        "11:00–12:00, 12:00–13:00, 13:00–14:00. Las restricciones son: "
    )
    variables = extract_variables_from_context(context)
    # Verificamos que la salida contenga las claves principales
    assert "variables" in variables, "La salida no contiene 'variables'."
    assert "decision_variables" in variables, "La salida no contiene 'decision_variables'."

    # Validación adicional: los valores extraídos deben tener tipos y rangos razonables
    assert isinstance(variables["variables"]["num_asignaturas"], int), "num_asignaturas debe ser un entero."
    assert variables["variables"]["num_asignaturas"] >= 5, "Se esperaban al menos 5 asignaturas."
    assert isinstance(variables["variables"]["dias"], int), "dias debe ser un entero."
    assert variables["variables"]["dias"] >= 5, "Se esperaban al menos 5 días."


def test_translate_constraint():
    # Creamos un conjunto ficticio de variables para un escenario complejo
    fake_variables = {
        "num_asignaturas": 5,
        "dias": 5,
        "franjas": 6,
        "horarios": ["08:00–09:00", "09:00–10:00", "10:00–11:00", "11:00–12:00", "12:00–13:00", "13:00–14:00"],
        "teoria": 2,
        "practica": 2,
    }
    # Restricción compleja que incluye bloques de 2 horas y evita solapamientos en franjas adyacentes
    nl_constraint = (
        "cada asignatura debe impartir 2 bloques de 2 horas, uno de teoría y otro de práctica, "
        "asegurando que no existan solapamientos en franjas adyacentes y que los bloques sean consecutivos en el mismo día"
    )
    codigo = translate_constraint_to_code(nl_constraint, fake_variables)
    # Verificamos que el código generado no esté vacío
    assert codigo, "El código traducido está vacío."
    # Intentamos compilar el código para asegurarnos de que es sintácticamente correcto
    try:
        compile(codigo, "<string>", "exec")
    except Exception as e:
        pytest.fail(f"El código traducido no compila: {e}")

    # Validación adicional: el código debe contener ciertos patrones esperados (por ejemplo, bucles o condicionales)
    assert "for" in codigo or "if" in codigo, "El código traducido debería incluir estructuras de control como 'for' o 'if'."


def test_extract_variables_minimal_context():
    """
    Verifica que, dado un contexto mínimo, se extraigan correctamente las variables
    y que se asuman valores mínimos lógicos.
    """
    context = "Planificar horario para 1 asignatura en 1 día, 1 franja: 08:00-09:00."
    variables = extract_variables_from_context(context)
    assert "variables" in variables, "La salida no contiene 'variables' en el contexto mínimo."
    assert "decision_variables" in variables, "La salida no contiene 'decision_variables' en el contexto mínimo."

    # Se espera que num_asignaturas y dias sean al menos 1
    assert isinstance(variables["variables"]["num_asignaturas"], int), "num_asignaturas debe ser un entero."
    assert variables["variables"]["num_asignaturas"] == 1, "Se esperaba 1 asignatura."
    assert isinstance(variables["variables"]["dias"], int), "dias debe ser un entero."
    assert variables["variables"]["dias"] == 1, "Se esperaba 1 día."
    # Verificar la existencia de la clave para franjas horarias (puede llamarse 'horarios' o 'horas')
    assert "horarios" in variables["variables"] or "horas" in variables["variables"], (
        "No se encontró clave para franjas horarias (horarios u horas)."
    )


def test_decision_variables_compilation():
    """
    Verifica que el código contenido en 'decision_variables' se compile correctamente.
    Esto garantiza que la parte de definición de variables de decisión es sintácticamente válida.
    """
    context = (
        "Planificar el horario para 3 asignaturas en 2 días con 4 franjas: 08:00-09:00, 09:00-10:00, 10:00-11:00, 11:00-12:00. "
        "Cada asignatura impartirá 2 horas de teoría y 2 horas de práctica."
    )
    variables = extract_variables_from_context(context)
    decision_code = variables.get("decision_variables")
    assert decision_code, "No se encontró código en 'decision_variables'."
    try:
        compile(decision_code, "<string>", "exec")
    except Exception as e:
        pytest.fail(f"El código en 'decision_variables' no compila: {e}")
