from gurobipy import Model, GRB, quicksum
import gurobipy as gp
import config
from utils.constraint_translator import translate_constraint_to_code


class ShiftOptimizer:
    def __init__(self, variables: dict):
        self.variables = variables
        self.model = Model("Optimizador General de Turnos")
        self.constraint_descriptions = {}

        # Local scope para exec
        local_scope = {
            "model": self.model,
            "GRB": GRB,
            "quicksum": quicksum,
            "gp": gp,
        }

        # Cargar variables dinámicamente
        for var_name, value in variables["variables"].items():
            try:
                value = int(value)
            except (ValueError, TypeError):
                pass  # Puede ser lista, dict, etc.
            setattr(self, var_name, value)
            local_scope[var_name] = value

        # Ejecutar definición de variables de decisión usando el mismo diccionario para globals y locals
        code = variables["decision_variables"].replace("self.model", "model").replace("self.", "")

        # Intentamos compilar y ejecutar el código de decisión con reintentos si falla
        max_attempts = config.MAX_ATTEMPTS
        attempt = 0
        while attempt < max_attempts:
            try:
                compiled_code = compile(code, "<string>", "exec")
                exec(compiled_code, local_scope)
                break  # Si se ejecuta correctamente, salimos del bucle
            except Exception as e:
                attempt += 1
                print(f"Intento {attempt} de compilar el código de 'decision_variables' fallido: {e}. Reintentando...")
        else:
            raise RuntimeError("No se pudo compilar el código de 'decision_variables' después de múltiples intentos.")

        # Detectar cualquier dict con claves tipo (int, int, int)
        for name, val in local_scope.items():
            if isinstance(val, dict) and all(isinstance(k, tuple) and len(k) == 3 for k in val.keys()):
                self.decision_vars = val
                break

        self.model.update()

    def obtener_contexto_ejecucion(self):
        """Construye un diccionario de contexto dinámico a partir de las variables definidas."""
        contexto = {
            "model": self.model,
            "quicksum": quicksum,
            "gp": gp,
        }
        for var_name in self.variables["variables"]:
            contexto[var_name] = getattr(self, var_name)
        if "x =" in self.variables["decision_variables"]:
            contexto["x"] = self.decision_vars
        elif "d =" in self.variables["decision_variables"]:
            contexto["d"] = self.decision_vars
        # Se asigna siempre el alias 'd_vars' para evitar conflictos en restricciones generadas
        contexto["d_vars"] = self.decision_vars
        return contexto

    def agregar_restriccion(self, nl_constraint: str, codigo_restriccion: str, max_attempts=config.MAX_ATTEMPTS):
        """
        Agrega una restricción al modelo a partir de código Gurobi.
        Si ocurre un error en tiempo de ejecución (por discrepancias de variables),
        vuelve a llamar a translate_constraint_to_code para retraducir la restricción,
        incluyendo el mensaje de error completo, y reintenta la ejecución hasta un máximo de intentos.
        Si se alcanza el máximo, retorna False para indicar que no se pudo agregar la restricción.
        """
        contexto = self.obtener_contexto_ejecucion()
        attempt = 0
        last_codigo = codigo_restriccion  # Guardamos el código original
        while attempt < max_attempts:
            print(f"Intentando agregar restricción, intento {attempt + 1}/{max_attempts}...")
            try:
                exec(last_codigo, contexto)
                # Tras ejecutar, identificamos las restricciones nuevas agregadas:
                nuevas_constr = [c for c in self.model.getConstrs() if c.constrName not in self.constraint_descriptions]
                for c in nuevas_constr:
                    self.constraint_descriptions[c.constrName] = nl_constraint
                print("Restricción agregada correctamente.")
                print("Código de restricción aceptado:")
                print(last_codigo)
                return True
            except Exception as e:
                attempt += 1
                error_str = str(e)
                print(f"Error al ejecutar la restricción (Intento {attempt}/{max_attempts}): {error_str}")
                # Se modifica el prompt incluyendo el error completo para que el modelo intente corregir la restricción
                nl_constraint_mod = (
                    nl_constraint
                    + "\nEl error completo es: " + error_str
                    + "\nCorrige la restricción para que funcione correctamente."
                )
                last_codigo = translate_constraint_to_code(nl_constraint_mod, self.variables["variables"])
        print("No se pudo agregar la restricción después de varios intentos. Por favor, ingresa otra restricción.")
        return False

    def definir_funcion_objetivo_balanceo(self, tipo_entidad="entidades", nombre_var="x"):
        """
        Minimiza la varianza de carga entre entidades (por ejemplo, profesores, retenes).
        Se adapta al nombre de la variable de decisión y entidades.
        """
        entidades = getattr(self, f"num_{tipo_entidad}", None)
        periodos = getattr(self, "dias", getattr(self, "num_periodos", None))
        slots = getattr(self, "num_franjas", getattr(self, "num_slots", None))

        if not all([entidades, periodos, slots]):
            print("⚠️ No se pueden aplicar balanceo: faltan dimensiones.")
            return

        carga = {e: self.model.addVar(vtype=GRB.CONTINUOUS, name=f"carga_{e}") for e in range(entidades)}

        for e in range(entidades):
            self.model.addConstr(
                carga[e] == quicksum(self.decision_vars[e, p, s] for p in range(periodos) for s in range(slots)),
                name=f"carga_total_{e}"
            )

        carga_media = quicksum(carga[e] for e in range(entidades)) / entidades
        varianza = quicksum((carga[e] - carga_media) ** 2 for e in range(entidades))
        self.model.setObjective(varianza, GRB.MINIMIZE)

    def optimizar(self):
        self.model.setParam("Threads", 1)
        self.model.setParam("Presolve", 0)
        self.model.setParam("MIPFocus", 2)

        # 🔁 Activar el solution pool
        self.model.setParam("PoolSearchMode", 2)
        self.model.setParam("PoolSolutions", 10)

        self.model.optimize()

        if self.model.status == GRB.OPTIMAL or self.model.status == GRB.SUBOPTIMAL:
            print(f"\n✅ Se encontraron {self.model.SolCount} soluciones factibles.")

            # Aquí usamos solo la mejor (la activa por defecto)
            print(f"\n🏆 Mejor solución encontrada (ObjVal = {self.model.ObjVal}):")
            for key, var in self.decision_vars.items():
                if var.X > 0.5:
                    print(f"  {key} -> {var.X}")

            return

        if self.model.status in (GRB.INFEASIBLE, GRB.INF_OR_UNBD):
            print("\n❌ El modelo es inviable. Analizando restricciones conflictivas...\n")
            self.model.computeIIS()
            for c in self.model.getConstrs():
                if c.IISConstr:
                    nl = self.constraint_descriptions.get(c.constrName, "Descripción no disponible")
                    print(f"🔍 Restricción conflictiva: {c.constrName}\n📝 Descripción: {nl}")

            print("\n⚠️ Intentando relajar las restricciones para encontrar una solución cercana...")
            orignumvars = self.model.NumVars
            self.model.feasRelaxS(relaxobjtype=0, minrelax=False, vrelax=False, crelax=True)

            self.model.optimize()
            if self.model.status == GRB.OPTIMAL:
                print("\n🔄 Modelo relajado resuelto con éxito.")
                print(f"📉 Objetivo (relajado): {self.model.ObjVal}")
                print("\n📊 Restricciones relajadas (valores de slack):")
                slacks = self.model.getVars()[orignumvars:]
                for sv in slacks:
                    if sv.X > 1e-6:
                        print(f"🔧 {sv.VarName} = {sv.X:g}")
            else:
                print("❌ El modelo relajado tampoco pudo resolverse.")
        else:
            print(f"\n⚠️ Optimización detenida. Estado: {self.model.status}")
