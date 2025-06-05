import tkinter as tk
from tkinter import messagebox
from tkinter import scrolledtext

from models.shift_optimizer import ShiftOptimizer
from utils.constraint_translator import extract_variables_from_context, translate_constraint_to_code
from utils.result_visualizer import exportar_resultados
import gurobipy as gp


def get_multiline_input(root, title: str, prompt: str, width=60, height=15) -> str | None:
    """
    Muestra un cuadro de diálogo modal con un Text de varias líneas.
    Devuelve el texto completo que el usuario introdujo (o None si canceló).
    """
    result = {"text": None}

    def on_ok():
        txt = text_widget.get("1.0", tk.END).rstrip()
        result["text"] = txt
        dialog.destroy()

    def on_cancel():
        dialog.destroy()

    dialog = tk.Toplevel(root)
    dialog.title(title)
    dialog.grab_set()  # Modal: bloquea interacción con la ventana principal
    dialog.geometry(f"{width * 8}x{height * 15}")

    label = tk.Label(dialog, text=prompt, justify=tk.LEFT, anchor="w")
    label.pack(padx=10, pady=(10, 0), anchor="w")

    text_widget = scrolledtext.ScrolledText(dialog, width=width, height=height, wrap=tk.WORD)
    text_widget.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

    btn_frame = tk.Frame(dialog)
    btn_frame.pack(pady=(0, 10))
    ok_button = tk.Button(btn_frame, text="Aceptar", width=10, command=on_ok)
    ok_button.pack(side=tk.LEFT, padx=5)
    cancel_button = tk.Button(btn_frame, text="Cancelar", width=10, command=on_cancel)
    cancel_button.pack(side=tk.LEFT, padx=5)

    # Centrar respecto a root
    dialog.update_idletasks()
    x = root.winfo_x() + (root.winfo_width() - dialog.winfo_width()) // 2
    y = root.winfo_y() + (root.winfo_height() - dialog.winfo_height()) // 2
    dialog.geometry(f"+{x}+{y}")

    root.wait_window(dialog)
    return result["text"]


if __name__ == "__main__":
    # Inicializar root de Tk y ocultarlo
    root = tk.Tk()
    root.withdraw()

    # 1) Pedir descripción del problema en un Text multiline
    context = get_multiline_input(
        root,
        "Descripción del problema",
        "Introduce la descripción completa del problema de planificación:"
    )
    if context is None or context.strip() == "":
        messagebox.showerror("Error", "No se proporcionó la descripción. Saliendo.")
        root.destroy()
        exit(1)

    # 2) Extraer variables/specs
    messagebox.showinfo("Procesando", "Extrayendo variables a partir del texto…")
    specs = extract_variables_from_context(context)
    if "error" in specs:
        messagebox.showerror("Error en extracción", specs["error"])
        root.destroy()
        exit(1)

    # (Opcional) imprimir por consola las specs para debug
    print("\n--- Variables extraídas (specs) ---")
    print(specs)
    print("------------------------------------\n")

    # 3) Crear instancia de ShiftOptimizer
    try:
        model = ShiftOptimizer(specs)
    except Exception as e:
        messagebox.showerror("Error al crear modelo", f"No se pudo inicializar ShiftOptimizer:\n{e}")
        root.destroy()
        exit(1)

    # 4) Pedir todas las restricciones a la vez, línea por línea
    constraints_text = get_multiline_input(
        root,
        "Restricciones",
        "Introduce todas las restricciones en lenguaje natural,\nuna por línea (se procesarán tras Aceptar):"
    )
    if constraints_text is None:
        messagebox.showinfo("Sin restricciones", "No se agregó ninguna restricción. Se procede a optimizar.")
        constraints_list = []
    else:
        # Dividir por líneas no vacías
        constraints_list = [line.strip() for line in constraints_text.splitlines() if line.strip()]

    # 5) Procesar cada restricción en orden
    for nl_constraint in constraints_list:
        # Traducir a código Gurobi
        code = translate_constraint_to_code(nl_constraint, specs)
        if isinstance(code, dict) and "error" in code:
            messagebox.showerror("Error en traducción",
                                 f"No se pudo traducir la restricción:\n'{nl_constraint}'\n\nError: {code['error']}")
            continue

        # Validar en modelo temporal
        valid = model.validar_restriccion(nl_constraint, code)
        if not valid:
            messagebox.showerror("Validación fallida",
                                 f"No se pudo validar la restricción tras varios intentos:\n'{nl_constraint}'")
            continue

        # Agregar al modelo principal
        added = model.agregar_restriccion(nl_constraint)
        if not added:
            messagebox.showwarning("No agregada",
                                   f"La restricción no pudo agregarse (quizá ya existe o está desactivada):\n'{nl_constraint}'")
        else:
            messagebox.showinfo("Añadida", f"Restricción agregada correctamente:\n'{nl_constraint}'")

    # 6) Ejecutar optimización
    messagebox.showinfo("Optimización", "Ejecutando optimización con Gurobi…")
    model.optimizar()

    # 7) Mostrar resultados
    if model.model.status == gp.GRB.OPTIMAL:
        activadas = [f"{var.VarName} = {var.X:g}" for var in model.model.getVars() if var.X > 0.5]
        resumen = "\n".join(activadas) if activadas else "No hay variables activadas."
        messagebox.showinfo(
            "Solución Óptima",
            f"Objetivo: {model.model.ObjVal:g}\n\nVariables activadas:\n{resumen}"
        )
        print("\n--- Variables activadas (>0.5) ---")
        for linea in activadas:
            print(" ·", linea)
        print("----------------------------------\n")
    else:
        messagebox.showwarning(
            "Sin solución óptima",
            f"El modelo no alcanzó solución óptima (estado Gurobi: {model.model.Status})."
        )

    # 8) Exportar a Excel
    try:
        exportar_resultados(model.model, model.decision_vars, specs)
        messagebox.showinfo("Exportación completada", "Resultados exportados a 'resultados_turnos.xlsx'.")
    except Exception as e:
        messagebox.showerror("Error al exportar", f"No se pudo exportar resultados:\n{e}")

    # Cerrar la aplicación
    root.destroy()
