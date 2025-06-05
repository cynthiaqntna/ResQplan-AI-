import pytest
import gurobipy as gp

from models.shift_optimizer import ShiftOptimizer
import utils.constraint_translator as ct


@pytest.fixture(autouse=True)
def patch_extract_and_translate(monkeypatch):
    """
    Parchea extract_variables_from_context y translate_constraint_to_code
    para que devuelvan especificaciones mínimas y un código trivial de restricción,
    de modo que ShiftOptimizer pueda construir el modelo pero las restricciones
    falsas provoquen inferasibilidades demostrables (ObjVal > 0 tras relajación).
    """

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
        # Bloque de decisión mínimo: una variable binaria
        "decision_variables": (
            "x_dummy = { (i, d, f): model.addVar(vtype=GRB.BINARY, name=f\"x_{i}_{d}_{f}\") "
            "for i in variables['lista_retenes'] for d in range(variables['dias']) for f in range(variables['franjas']) }"
        ),
    }

    def fake_extract(context):
        return dummy_specs.copy()

    def fake_translate(nl_constraint, specs):
        """
        Si en el texto NL aparece 'mínimo 10' o '8 horas',
        genera una expresión imposible: quicksum(x_dummy.values()) >= 10.
        En caso contrario, genera quicksum(x_dummy.values()) <= 2.
        """
        if "mínimo de 10 retenes" in nl_constraint or "mínimo de 10 enfermeras" in nl_constraint or "8 horas" in nl_constraint:
            return "model.addConstr(quicksum(x_dummy.values()) >= 10, name='infeasible')"
        else:
            return "model.addConstr(quicksum(x_dummy.values()) <= 2, name='normal')"

    monkeypatch.setattr(ct, "extract_variables_from_context", fake_extract)
    monkeypatch.setattr(ct, "translate_constraint_to_code", fake_translate)
    yield


@pytest.fixture
def emergency_context():
    return "GESTIÓN DE TURNOS – EMERGENCIAS: Se requiere planificar los turnos para retenes contra incendios..."


@pytest.fixture
def academic_context():
    return "PLANIFICACIÓN DEL HORARIO SEMANAL: Se requiere planificar el horario para el primer curso..."


@pytest.fixture
def hospital_context():
    return "PLANIFICACIÓN DE TURNOS HOSPITALARIOS: Se requiere planificar los turnos de enfermería para el Hospital..."


def test_emergency_infeasible(emergency_context):
    variables = ct.extract_variables_from_context(emergency_context)
    assert "variables" in variables
    assert "decision_variables" in variables

    model = ShiftOptimizer(variables)

    # Restricciones 'normales' (no bloquean)
    normal_nl = "el número mínimo de retenes es 6 y el máximo 8 por turno"
    normal_code = ct.translate_constraint_to_code(normal_nl, variables["variables"])
    assert "quicksum(x_dummy.values()) <= 2" in normal_code
    assert model.validar_restriccion(normal_nl, normal_code)
    assert model.agregar_restriccion(normal_nl)

    descanso_nl = "un retén solo puede trabajar dos días seguidos y luego debe descansar 1"
    descanso_code = ct.translate_constraint_to_code(descanso_nl, variables["variables"])
    assert "quicksum(x_dummy.values()) <= 2" in descanso_code
    assert model.validar_restriccion(descanso_nl, descanso_code)
    assert model.agregar_restriccion(descanso_nl)

    # Restricción imposible (mínimo 10 retenes)
    infeasible_nl = "el número mínimo de 10 retenes por turno"
    infeasible_code = ct.translate_constraint_to_code(infeasible_nl, variables["variables"])
    assert ">= 10" in infeasible_code
    assert model.validar_restriccion(infeasible_nl, infeasible_code)
    assert model.agregar_restriccion(infeasible_nl)

    model.optimizar()
    assert model.model.status == gp.GRB.OPTIMAL
    assert model.model.ObjVal > 0  # Indica que se relajaron restricciones


def test_academic_schedule_infeasible(academic_context):
    variables = ct.extract_variables_from_context(academic_context)
    assert "variables" in variables
    assert "decision_variables" in variables

    model = ShiftOptimizer(variables)

    # Restricciones 'normales'
    carga_nl = "cada asignatura se impartirá exactamente 4 horas semanales"
    carga_code = ct.translate_constraint_to_code(carga_nl, variables["variables"])
    assert "quicksum(x_dummy.values()) <= 2" in carga_code
    assert model.validar_restriccion(carga_nl, carga_code)
    assert model.agregar_restriccion(carga_nl)

    solap_nl = "en cada franja horaria solo se podrá impartir una asignatura"
    solap_code = ct.translate_constraint_to_code(solap_nl, variables["variables"])
    assert "quicksum(x_dummy.values()) <= 2" in solap_code
    assert model.validar_restriccion(solap_nl, solap_code)
    assert model.agregar_restriccion(solap_nl)

    # Restricción imposible: exactamente 8 horas
    infeasible_nl = "cada asignatura se impartirá exactamente 8 horas semanales"
    infeasible_code = ct.translate_constraint_to_code(infeasible_nl, variables["variables"])
    assert ">= 10" in infeasible_code
    assert model.validar_restriccion(infeasible_nl, infeasible_code)
    assert model.agregar_restriccion(infeasible_nl)

    model.optimizar()
    assert model.model.status == gp.GRB.OPTIMAL
    assert model.model.ObjVal > 0  # Hubo relajación


def test_hospital_schedule_infeasible(hospital_context):
    variables = ct.extract_variables_from_context(hospital_context)
    assert "variables" in variables
    assert "decision_variables" in variables

    model = ShiftOptimizer(variables)

    # Restricciones 'normales'
    num_nl = "cada turno debe contar con un mínimo de 5 y un máximo de 7 enfermeras"
    num_code = ct.translate_constraint_to_code(num_nl, variables["variables"])
    assert "quicksum(x_dummy.values()) <= 2" in num_code
    assert model.validar_restriccion(num_nl, num_code)
    assert model.agregar_restriccion(num_nl)

    descanso_nl = "cada enfermera debe tener un descanso mínimo de 12 horas entre turnos consecutivos"
    descanso_code = ct.translate_constraint_to_code(descanso_nl, variables["variables"])
    assert "quicksum(x_dummy.values()) <= 2" in descanso_code
    assert model.validar_restriccion(descanso_nl, descanso_code)
    assert model.agregar_restriccion(descanso_nl)

    # Restricción imposible: mínimo 10 enfermeras
    infeasible_nl = "cada turno debe contar con un mínimo de 10 enfermeras"
    infeasible_code = ct.translate_constraint_to_code(infeasible_nl, variables["variables"])
    assert ">= 10" in infeasible_code
    assert model.validar_restriccion(infeasible_nl, infeasible_code)
    assert model.agregar_restriccion(infeasible_nl)

    model.optimizar()
    assert model.model.status == gp.GRB.OPTIMAL
    assert model.model.ObjVal > 0  # Se relajaron restricciones
