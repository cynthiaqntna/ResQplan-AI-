# 🔥 ResqPlan-AI

ResqPlan-AI es una herramienta de optimización de turnos basada en Gurobi y OpenAI que permite, a partir de una descripción en lenguaje natural, extraer automáticamente las variables del problema y traducir restricciones en lenguaje natural a código Gurobi. Está diseñada para conectarse con una interfaz externa de ingreso de datos (por ejemplo, un sistema web o una aplicación cliente) sin necesidad de crear una interfaz completa en este repositorio.

---

## 📋 Contenido del repositorio

- `main.py`  
  Punto de entrada que abre un cuadro de diálogo minimalista en Tkinter para que el usuario ingrese:
  1. La descripción global del problema (horarios, recursos, franjas, etc.).
  2. Múltiples restricciones en lenguaje natural (cada línea representa una restricción).  
  Tras pulsar “OK”, todas las restricciones se traducen y validan automáticamente, y luego el modelo se optimiza en bloque.  
  > **Nota**: Este script se puede reemplazar o adaptar para recibir datos desde cualquier interfaz externa (web, móvil, etc.), enviando la descripción y las restricciones en un solo bloque de texto.

- `models/shift_optimizer.py`  
  Clase `ShiftOptimizer` que:
  1. Recibe un diccionario de especificaciones (`specs`), que contiene `variables`, `resources` y un bloque de `decision_variables` como string.  
  2. Construye el modelo de Gurobi, crea las variables de decisión y mantiene un contexto de ejecución dinámico.  
  3. Valida cada restricción en un modelo temporal (evitando errores de sintaxis o errores lógicos antes de inyectar al modelo principal).  
  4. Agrega las restricciones validadas al modelo principal y conserva mapeos de nombres de restricción → línea NL original.  
  5. Optimiza el modelo, detecta infeasibilidades e intenta una relajación automática (`IIS + feasRelaxS`) si es necesario.

- `utils/constraint_translator.py`  
  Contiene dos funciones principales:
  1. **`extract_variables_from_context(context: str) -> dict`**  
     Usa la API de OpenAI para analizar la descripción del problema en lenguaje natural y devolver un JSON con:
     - `variables`: diccionario con `dias`, `franjas`, `horarios` y listas de cada tipo de entidad (retenes, enfermeras, asignaturas…).  
     - `resources`: diccionario de cantidades de recursos disponibles.  
     - `decision_variables`: un bloque de Python (string) que crea todas las variables de decisión en Gurobi (`model.addVar`), devolviendo un `tupledict` o `dict`.  
     - `detected_constraints`: (opcional) lista de oraciones del texto que se detectaron como restricciones automáticamente.  
     En caso de error o contexto no válido, devuelve un JSON con clave `"error"` describiendo el problema.  
     > **Conexión externa**: esta función se puede invocar desde cualquier cliente (por ejemplo, un servicio web) enviando el texto completo del problema y recibiendo el JSON listo para instanciar `ShiftOptimizer`.

  2. **`translate_constraint_to_code(nl_constraint: str, specs: dict) -> str|dict`**  
     Dada una restricción en lenguaje natural y el JSON de `specs`, invoca la API de OpenAI para generar un bloque de código Python que:
     - Utilice `model.addConstr(...)` y `quicksum(...)` adecuadamente.  
     - Nombre cada restricción con `name="..."` (snake_case basado en la frase original).  
     - Devuelva un JSON de la forma `{"error": "..."}` si la restricción no aplica o no se ajusta al contexto.  
     Se reintenta la traducción hasta `MAX_ATTEMPTS` veces en caso de errores de compilación.

- `utils/result_visualizer.py`  
  Función `exportar_resultados(model, decision_vars, specs)` que:
  1. Recorre las variables de decisión con `var.X > 0.5`.  
  2. Construye un DataFrame de pandas con columnas “Día”, “Turno” y “Elementos” (entidades asignadas).  
  3. Exporta la información a un archivo Excel (`.xlsx`) con formato básico (colores, bordes).  
  > Se puede adaptar para enviar resultados a una interfaz externa (por ejemplo, retornando un DataFrame o un JSON).

- `config.py`  
  Contiene parámetros globales, como `MAX_ATTEMPTS`, para el número máximo de reintentos en la traducción de restricciones.


# 📦 requirements.txt

Lista de dependencias necesarias para ejecutar ShiftOptimizer:

- `gurobipy`: Cliente Python de Gurobi para crear y resolver el modelo de optimización.
- `openai`: Cliente que se comunica con la API de OpenAI para traducir texto en lenguaje natural a código Python.
- `pandas`: Para construir un DataFrame con el resumen de resultados (Día, Turno, Elementos).
- `xlsxwriter`: Motor que usa pandas para exportar el DataFrame a un archivo Excel (.xlsx).

---

# 🚀 Uso en modo GUI mínimo

Ejecutar el script principal:

```bash
python main.py
```

## Descripción del problema

Aparecerá un cuadro emergente titulado “Descripción del problema”.

Ingresa o pega todo el texto completo, por ejemplo:

```csharp
GESTIÓN DE TURNOS – EMERGENCIAS: Se requiere planificar los turnos para retenes contra incendios en situaciones de emergencia para un periodo de 6 días. ...
```

Pulsa OK.

## Extracción de variables

Se mostrará un mensaje indicando:

```
Extrayendo variables a partir del texto…
```

Internamente, `extract_variables_from_context` invoca la API de OpenAI y devuelve un diccionario con las claves:

- `variables`
- `resources`
- `decision_variables`
- `detected_constraints` (opcional)

Si hay error, se mostrará un cuadro con el mensaje correspondiente.

## Ingreso en bloque de restricciones

Aparecerá un cuadro de texto multilínea (“Nueva restricción”) donde puedes pegar varias restricciones separadas por salto de línea:

```python
el número mínimo de retenes es 6 y el máximo 8 por turno
un retén solo puede trabajar dos días seguidos y luego debe descansar 1
los dos turnos consecutivos deben ser del mismo tipo y, tras el descanso, deben ser del turno contrario
```

Pulsa OK.

El programa leerá cada línea, llamará a `translate_constraint_to_code`, validará y agregará cada restricción al modelo.

## Optimización

Se mostrará un mensaje:

```
Ejecutando optimización…
```

Si el modelo es factible, se mostrará:

```yaml
Objetivo: <valor_objetivo>
Variables activadas:
  x_<...> = 1
  ...
```

Si es infactible, se calcula el IIS y se ejecuta `feasRelaxS()`. Se mostrará:

```php-template
Modelo relajado resuelto. Objetivo: <valor_relajado>
Frases de restricciones relajadas:
  - <frase1>
  - <frase2>
```

## Exportación a Excel

Después de optimizar, se exporta el archivo `resultados_turnos.xlsx`.

Un cuadro confirmará:

```
Resultados exportados a 'resultados_turnos.xlsx'
```

---

# 📐 Estructura de datos (`specs`)

El JSON `specs` que utiliza ShiftOptimizer debe tener la forma:

```jsonc
{
  "variables": {
    "dias": 6,
    "franjas": 2,
    "horarios": ["Diurno", "Nocturno"],
    "lista_retenes": ["R1", "R2", …],
    "lista_enfermeras": ["E1", "E2", …],
    "lista_asignaturas": ["A1", "A2", …]
  },
  "resources": {
    // Ejemplo: "retenes": 11, "enfermeras": 20, "profesores": 5
  },
  "decision_variables": "<string Python válido>",
  "detected_constraints": []
}
```

El bloque `decision_variables` debe crear variables de decisión con `model.addVar(...)` y devolver un `tupledict` o `dict` con claves que empiecen con `"x_"`.

---

# 📖 Ejemplo de restricciones que OpenAI traduce y envía al modelo

### Un retén solo puede trabajar en un turno por día

```python
for r in range(self.num_retenes):
    for d in range(self.dias):
        self.model.addConstr(
            quicksum(self.x[r, d, t] for t in range(self.num_turnos)) <= 1,
            name=f"reten_{r}_un_turno_dia_{d}"
        )
```

### Entre 3 y 4 retenes activos por turno

```python
for d in range(self.dias):
    for t in range(self.num_turnos):
        expr = quicksum(self.x[r, d, t] for r in range(self.num_retenes))
        self.model.addConstr(expr <= self.max_activos, name=f"max_retenes_turno_{d}_{t}")
        self.model.addConstr(expr >= 3, name=f"min_retenes_turno_{d}_{t}")
```

### Descanso mínimo de 12 horas antes de reincorporarse

```python
for r in range(self.num_retenes):
    for d in range(self.dias - 1):
        self.model.addConstr(
            self.x[r, d, 1] + self.x[r, (d + 1) % self.dias, 0] <= 1,
            name=f"descanso_minimo_{r}_dia_{d}"
        )
```

### Ciclo de turnos ideal: Noche, Noche, Descanso, Mañana, Mañana, Descanso

```python
for r in range(self.num_retenes):
    for d in range(self.dias - 5):
        self.model.addConstr(
            self.x[r, d, 1] + self.x[r, d+1, 1] + self.x[r, d+2, 0] +
            self.x[r, d+3, 0] + self.x[r, d+4, 1] + self.x[r, d+5, 1] <= 2,
            name=f"ciclo_turnos_ideal_{r}_dia_{d}"
        )
```

### Evitar relevos nocturnos a mitad de la noche

```python
for r in range(self.num_retenes):
    for d in range(self.dias):
        self.model.addConstr(
            self.x[r, d, 1] <= self.x[r, d, 0] + 1,
            name=f"evitar_relevos_noche_{r}_dia_{d}"
        )
```

### Solapamiento de turnos hasta las 17:30

```python
for d in range(self.dias):
    self.model.addConstr(
        quicksum(self.x[r, d, 0] for r in range(self.num_retenes)) >=
        quicksum(self.x[r, d, 1] for r in range(self.num_retenes)),
        name=f"solapamiento_turnos_{d}"
    )
```

### Relevos dinámicos en función del desgaste

```python
for r in range(self.num_retenes):
    for d in range(self.dias):
        self.model.addConstr(
            quicksum(self.x[r, d - i, t]
                     for i in range(3)
                     for t in range(self.num_turnos)
                     if d - i >= 0) <= 2,
            name=f"relevos_dinamicos_{r}_dia_{d}"
        )
```


# 📝 Notas finales

- **Validación en runtime**: Cada restricción en NL se compila y valida en un modelo temporal con `validar_restriccion()`. Si falla, se reintenta traducir con contexto del error hasta `MAX_ATTEMPTS`.
- **Relajación automática**: Si el modelo es infactible, se calcula el IIS y se ejecuta `model.feasRelaxS()`. El usuario recibe un listado de restricciones que se “relajaron” (`slacks`).
- **Conexión con interfaz externa**: Aunque este repositorio provee un ejemplo minimalista en Tkinter (`main.py`), es sencillo adaptar el flujo para recibir la descripción del problema y las restricciones desde cualquier sistema externo (servicio web, app, bot, etc.).
- **Exportación**: Los resultados se guardan en `resultados_turnos.xlsx` con formato de tabla que muestra “Día”, “Turno” y “Elementos asignados”. También se puede adaptar para devolver un `DataFrame` o un `JSON` al frontend.

