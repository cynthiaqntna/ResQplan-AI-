import pandas as pd
import os


def exportar_resultados(model, decision_vars, variables, archivo_salida=None):
    if archivo_salida is None:
        archivo_salida = os.path.join(os.getcwd(), "resultados_turnos.xlsx")

    params = variables["variables"]
    horarios = params.get("horarios", [])
    nombres_dias = params.get("nombres_dias", [])
    dias = params.get("dias", 0)

    reverse_map = {}
    for nombre_lista, lista in params.items():
        if nombre_lista.startswith("lista_") and isinstance(lista, list):
            for item in lista:
                reverse_map[item] = nombre_lista.replace("lista_", "")

    filas = []
    # CAMBIO AQUÍ: iterar sobre (key, var) directamente
    for key, var in decision_vars.items():
        if var.X > 0.5:
            *entidades, dia_idx, franja_idx = key
            dia_hum = nombres_dias[dia_idx] if dia_idx < len(nombres_dias) else f"Día {dia_idx + 1}"
            turno = horarios[franja_idx] if franja_idx < len(horarios) else f"Turno {franja_idx}"
            elementos = []
            for valor in entidades:
                elementos.append(valor)
            filas.append({
                "Día": dia_hum,
                "Turno": turno,
                "Elementos": " / ".join(sorted(elementos))
            })

    df = pd.DataFrame(filas)

    if not df.empty:
        df_resumen = df.groupby(["Turno", "Día"])["Elementos"] \
                       .apply(lambda x: " / ".join(x)) \
                       .unstack(fill_value="Descanso")
    else:
        df_resumen = pd.DataFrame()

    with pd.ExcelWriter(archivo_salida, engine="xlsxwriter") as writer:
        df_resumen.to_excel(writer, sheet_name="Resumen")

        workbook = writer.book
        header_format = workbook.add_format({"bold": True, "bg_color": "#D9EAD3", "border": 1})
        cell_format = workbook.add_format({"border": 1})
        descanso_format = workbook.add_format({"bg_color": "#F4CCCC", "border": 1})

        worksheet = writer.sheets["Resumen"]

        for col_num, value in enumerate(df_resumen.columns.values):
            worksheet.write(0, col_num + 1, value, header_format)
            worksheet.set_column(col_num + 1, col_num + 1, 40)

        for row_num, value in enumerate(df_resumen.index.values):
            worksheet.write(row_num + 1, 0, value, header_format)

        for row in range(df_resumen.shape[0]):
            for col in range(df_resumen.shape[1]):
                cell_value = df_resumen.iloc[row, col]
                fmt = cell_format if cell_value != "Descanso" else descanso_format
                worksheet.write(row + 1, col + 1, cell_value, fmt)

    print(f"✅ Resultados exportados a: {archivo_salida}")
