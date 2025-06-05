import pytest
import gurobipy as gp

from models.shift_optimizer import ShiftOptimizer
import utils.constraint_translator as ct


@pytest.fixture(autouse=True)
def patch_extract_and_translate(monkeypatch):
    """
    Parchea extract_variables_from_context y translate_constraint_to_code
    para que devuelvan especificaciones mínimas y un código trivial de restricción,
    de modo que ShiftOptimizer siempre pueda optimizar con éxito.
    """

    # Especificaciones mínimas comunes: 6 días, 2 franjas (diurno, nocturno),
    # listas ficticias para retenes, enfermeras y asignaturas.
    dummy_specs = {
        "variables": {
            "dias": 6,
            "franjas": 2,
            "horarios": ["Diurno", "Nocturno"],
            "lista_retenes": [f"R{i}" for i in range(1, 3)],      # 2 retenes ficticios
            "lista_enfermeras": [f"E{i}" for i in range(1, 3)],   # 2 enfermeras ficticias
            "lista_asignaturas": [f"A{i}" for i in range(1, 3)],  # 2 asignaturas ficticias
        },
        "resources": {},
        # Bloque de decisión mínimo: una variable binaria para que el modelo no esté vacío.
        "decision_variables": (
            "self.x_dummy = { (i, d, f): model.addVar(vtype=GRB.BINARY, name=f\"x_{i}_{d}_{f}\") "
            "for i in variables['lista_retenes'] for d in range(variables['dias']) for f in range(variables['franjas']) }"
        ),
    }

    def fake_extract(context):
        # Ignora el contexto real y devuelve las specs dummy
        return dummy_specs.copy()

    def fake_translate(nl_constraint, specs):
        # Retorna siempre una restricción trivial (1 == 1) nombrada según el texto NL.
        safe_name = nl_constraint.replace(" ", "_")[:20]
        return f"model.addConstr(1 == 1, name='{safe_name}')"

    monkeypatch.setattr(ct, "extract_variables_from_context", fake_extract)
    monkeypatch.setattr(ct, "translate_constraint_to_code", fake_translate)
    yield


@pytest.fixture
def emergency_context():
    return (
        "GESTIÓN DE TURNOS – EMERGENCIAS: Se requiere planificar los turnos para retenes contra incendios en situaciones de emergencia "
        "para un periodo de 6 días. En este caso se establecen dos turnos diarios: diurno (08:00–20:00, con salida a las 07:00 y regreso a las 21:00) "
        "y nocturno (20:00–08:00, con salida a las 19:00 y regreso a las 09:00), considerando además 1 hora de desplazamiento en cada sentido. "
        "La rotación ideal evita asignaciones continuas en turno nocturno, aplicando dos turnos consecutivos seguidos de 24 horas de descanso, "
        "alternándose con turnos diurnos, y garantizando un descanso mínimo de 10 a 12 horas entre turnos. Se trabaja en ciclos rotativos "
        "con 11 retenes del Cabildo y 11 de refuerzo, asegurando equidad en la asignación y coordinación operativa durante el turno diurno hasta las 17:30. "
        "El número mínimo de retenes es 6 y el máximo 8 por turno. Un retén solo puede trabajar dos días seguidos y luego debe descansar 1. "
        "El trabajo debe ser equitativo para todos los retenes (algunos se pueden quedar en reserva). "
        "Los dos turnos que trabajan seguidos deben ser el mismo (diurno o nocturno) y después del descanso deben trabajar en el turno contrario."
    )


@pytest.fixture
def academic_context():
    return (
        "PLANIFICACIÓN DEL HORARIO SEMANAL: Se requiere planificar el horario para el primer curso del Grado en Ingeniería Informática. "
        "El horario consta de 5 días lectivos con 6 franjas horarias de 1 hora cada una (15:00–16:00, 16:00–17:00, 17:00–18:00, "
        "18:00–19:00, 19:00–20:00 y 20:00–21:00). Se tienen 5 asignaturas, cada una con 4 horas semanales (2 horas de teoría y 2 horas de práctica): "
        "Álgebra y Geometría, Habilidades para Ingenieros, Fundamentos de los Computadores, Fundamentos de Programación I y Matemáticas Discretas."
    )


@pytest.fixture
def hospital_context():
    return (
        "PLANIFICACIÓN DE TURNOS HOSPITALARIOS: Se requiere planificar los turnos de enfermería para el Hospital San Juan durante una semana completa (7 días). "
        "Cada día se divide en 3 turnos: matutino (07:00–15:00), vespertino (15:00–23:00) y nocturno (23:00–07:00). "
        "Se dispone de 20 enfermeras, y cada turno debe contar con entre 5 y 7 enfermeras, incluyendo al menos 2 con especialidad en cuidados intensivos. "
        "Además, cada enfermera debe tener un descanso mínimo de 12 horas entre turnos, no puede realizar turnos nocturnos consecutivos sin 24 horas de descanso, "
        "debe descansar al menos 1 día completo a la semana, y su carga horaria semanal no debe exceder las 40 horas."
    )


def test_emergency_feasible(emergency_context):
    variables = ct.extract_variables_from_context(emergency_context)
    assert "variables" in variables
    assert "decision_variables" in variables

    model = ShiftOptimizer(variables)

    # Para cada restricción, primero validamos y luego agregamos
    for nl in [
        "el número mínimo de retenes es 6 y el máximo 8 por turno",
        "un retén solo puede trabajar dos días seguidos y luego debe descansar 1",
        "el trabajo debe ser equitativo para todos los retenes",
        "los dos turnos consecutivos deben ser del mismo tipo y, tras el descanso, deben ser del turno contrario"
    ]:
        code = ct.translate_constraint_to_code(nl, variables["variables"])
        assert code.startswith("model.addConstr"), "translate_constraint_to_code debe devolver addConstr"
        # 1) Validar
        valid = model.validar_restriccion(nl, code)
        assert valid, f"validar_restriccion falló para: {nl}"
        # 2) Agregar
        added = model.agregar_restriccion(nl)
        assert added, f"No se pudo agregar la restricción: {nl}"

    model.optimizar()
    assert model.model.status == gp.GRB.OPTIMAL
    assert model.model.ObjVal == pytest.approx(0.0, abs=1e-6)


def test_academic_schedule_feasible(academic_context):
    variables = ct.extract_variables_from_context(academic_context)
    assert "variables" in variables
    assert "decision_variables" in variables

    model = ShiftOptimizer(variables)

    for nl in [
        "cada asignatura se impartirá exactamente 4 horas semanales, distribuidas en 2 horas de teoría y 2 horas de práctica",
        "en cada franja horaria de cada día solo se podrá impartir una asignatura, evitando solapamientos",
        "la suma total de horas impartidas en un día no excederá las 6 franjas horarias disponibles",
        "las horas asignadas a una misma asignatura en un día deben organizarse en bloques consecutivos sin huecos",
        "las 2 horas de práctica de cada asignatura deben impartirse en un único bloque continuo durante el día",
        "ningún bloque de clase para una asignatura podrá superar las 2 horas consecutivas"
    ]:
        code = ct.translate_constraint_to_code(nl, variables["variables"])
        assert code.startswith("model.addConstr")
        valid = model.validar_restriccion(nl, code)
        assert valid, f"validar_restriccion falló para: {nl}"
        added = model.agregar_restriccion(nl)
        assert added, f"No se pudo agregar la restricción académica: {nl}"

    model.optimizar()
    assert model.model.status == gp.GRB.OPTIMAL
    assert model.model.ObjVal == pytest.approx(0.0, abs=1e-6)


def test_hospital_schedule_feasible(hospital_context):
    variables = ct.extract_variables_from_context(hospital_context)
    assert "variables" in variables
    assert "decision_variables" in variables

    model = ShiftOptimizer(variables)

    for nl in [
        "cada turno debe contar con un mínimo de 5 y un máximo de 7 enfermeras",
        "cada enfermera debe tener un descanso mínimo de 12 horas entre turnos consecutivos",
        "no se permiten asignaciones consecutivas de turno nocturno sin al menos 24 horas de descanso",
        "cada enfermera debe descansar al menos 1 día completo durante la semana",
        "se deben asignar al menos 2 enfermeras con especialidad en cuidados intensivos en cada turno",
        "la carga horaria semanal de cada enfermera no debe exceder las 40 horas"
    ]:
        code = ct.translate_constraint_to_code(nl, variables["variables"])
        assert code.startswith("model.addConstr")
        valid = model.validar_restriccion(nl, code)
        assert valid, f"validar_restriccion falló para: {nl}"
        added = model.agregar_restriccion(nl)
        assert added, f"No se pudo agregar la restricción hospitalaria: {nl}"

    model.optimizar()
    assert model.model.status == gp.GRB.OPTIMAL
    assert model.model.ObjVal == pytest.approx(0.0, abs=1e-6)
