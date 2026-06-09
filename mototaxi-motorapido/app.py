
import sqlite3
import os
from flask import Flask, request, jsonify, g
from datetime import datetime


BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(BASE_DIR, "motorapido.db")

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")

#  BASE DE DATOS SQLite
def get_db():
    """Devuelve la conexión a la base de datos (una por request)."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row   # permite acceder por nombre de columna
    return g.db


@app.teardown_appcontext
def cerrar_db(error):
    """Cierra la conexión al terminar cada request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def inicializar_db():
    """Crea las tablas si no existen."""
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS reservas (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre    TEXT    NOT NULL,
            telefono  TEXT    NOT NULL,
            origen    TEXT    NOT NULL,
            destino   TEXT    NOT NULL,
            fecha     TEXT    NOT NULL,
            hora      TEXT    NOT NULL,
            servicio  TEXT    NOT NULL,
            estado    TEXT    NOT NULL DEFAULT 'pendiente',
            precio    REAL,
            creado    TEXT    NOT NULL
        )
    """)
    db.commit()
    db.close()
    print("  ✅ Base de datos lista:", DB_PATH)

TARIFAS = {
    "Centro":     {"precio": 8,  "tiempo": "5 - 10 min",  "distancia": "0 - 3 km"},
    "Norte":      {"precio": 12, "tiempo": "10 - 15 min", "distancia": "3 - 6 km"},
    "Sur":        {"precio": 18, "tiempo": "15 - 25 min", "distancia": "6 - 10 km"},
    "Este/Oeste": {"precio": 25, "tiempo": "25 - 35 min", "distancia": "10 - 15 km"},
}

SERVICIOS_VALIDOS = ["viaje", "delivery", "mensajeria"]
ESTADOS_VALIDOS   = ["pendiente", "confirmado", "en camino", "completado", "cancelado"]


# ================================================================
#  FUNCIONES AUXILIARES
# ================================================================

def fila_a_dict(fila):
    """Convierte una fila de SQLite (Row) a diccionario."""
    return dict(fila) if fila else None


def validar_campos(datos, campos):
    """Valida que todos los campos requeridos estén presentes y no vacíos."""
    for campo in campos:
        if not datos.get(campo, "").strip():
            return False, campo
    return True, None


def calcular_precio(origen, destino):
    """
    Estima el precio buscando palabras clave de zona en origen/destino.
    Si no encuentra zona, devuelve tarifa base de Centro.
    """
    texto = (origen + " " + destino).lower()
    if "norte" in texto:
        return TARIFAS["Norte"]["precio"]
    elif "sur" in texto:
        return TARIFAS["Sur"]["precio"]
    elif "este" in texto or "oeste" in texto:
        return TARIFAS["Este/Oeste"]["precio"]
    else:
        return TARIFAS["Centro"]["precio"]


# ================================================================
#  RUTA PRINCIPAL
# ================================================================

@app.route("/")
def inicio():
    """Sirve la página principal index.html."""
    return app.send_static_file("index.html")


# ================================================================
#  RUTAS DE RESERVAS
# ================================================================

@app.route("/reservar", methods=["POST"])
def reservar():
    """
    Crea una nueva reserva de moto taxi.

    Recibe (JSON):
        nombre, telefono, origen, destino, fecha, hora, servicio

    Devuelve (JSON):
        { ok, mensaje, id, precio }
    """
    datos = request.get_json(silent=True)
    if not datos:
        return jsonify({"error": "No se recibieron datos JSON."}), 400

    # -- Validación de campos obligatorios --
    campos_requeridos = ["nombre", "telefono", "origen", "destino",
                         "fecha", "hora", "servicio"]
    ok, campo_faltante = validar_campos(datos, campos_requeridos)
    if not ok:
        return jsonify({"error": f"El campo '{campo_faltante}' es obligatorio."}), 400

    # -- Validar servicio --
    if datos["servicio"] not in SERVICIOS_VALIDOS:
        return jsonify({"error": f"Servicio no válido. Opciones: {SERVICIOS_VALIDOS}"}), 400

    # -- Validar formato de fecha --
    try:
        datetime.strptime(datos["fecha"], "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD."}), 400

    # -- Calcular precio estimado --
    precio = calcular_precio(datos["origen"], datos["destino"])

    # -- Guardar en base de datos --
    db    = get_db()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor = db.execute("""
        INSERT INTO reservas (nombre, telefono, origen, destino,
                              fecha, hora, servicio, estado, precio, creado)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente', ?, ?)
    """, (
        datos["nombre"].strip(),
        datos["telefono"].strip(),
        datos["origen"].strip(),
        datos["destino"].strip(),
        datos["fecha"].strip(),
        datos["hora"].strip(),
        datos["servicio"].strip(),
        precio,
        ahora,
    ))
    db.commit()
    nueva_id = cursor.lastrowid

    # -- Log en consola --
    print(f"\n  🏍️  Nueva reserva #{nueva_id}")
    print(f"     Cliente : {datos['nombre']}  |  {datos['telefono']}")
    print(f"     Ruta    : {datos['origen']}  →  {datos['destino']}")
    print(f"     Fecha   : {datos['fecha']} a las {datos['hora']}")
    print(f"     Servicio: {datos['servicio']}  |  Precio estimado: Bs. {precio}\n")

    mensaje = (
        f"¡Gracias {datos['nombre']}! "
        f"Tu viaje de {datos['origen']} → {datos['destino']} "
        f"fue reservado para el {datos['fecha']} a las {datos['hora']}. "
        f"Precio estimado: Bs. {precio}. "
        f"Te contactamos al {datos['telefono']}."
    )

    return jsonify({"ok": True, "mensaje": mensaje, "id": nueva_id, "precio": precio})


# ----------------------------------------------------------------

@app.route("/reservas", methods=["GET"])
def ver_reservas():
    """
    Devuelve todas las reservas en JSON.
    Parámetros opcionales de URL:
        ?estado=pendiente    filtra por estado
        ?fecha=2025-06-01    filtra por fecha
    """
    db     = get_db()
    estado = request.args.get("estado", "").strip()
    fecha  = request.args.get("fecha", "").strip()

    consulta = "SELECT * FROM reservas WHERE 1=1"
    params   = []

    if estado:
        consulta += " AND estado = ?"
        params.append(estado)
    if fecha:
        consulta += " AND fecha = ?"
        params.append(fecha)

    consulta += " ORDER BY id DESC"

    filas    = db.execute(consulta, params).fetchall()
    lista    = [fila_a_dict(f) for f in filas]

    return jsonify({"total": len(lista), "reservas": lista})


# ----------------------------------------------------------------

@app.route("/reservas/<int:reserva_id>", methods=["GET"])
def ver_reserva(reserva_id):
    """Devuelve una reserva específica por ID."""
    db   = get_db()
    fila = db.execute("SELECT * FROM reservas WHERE id = ?", (reserva_id,)).fetchone()
    if not fila:
        return jsonify({"error": f"Reserva #{reserva_id} no encontrada."}), 404
    return jsonify(fila_a_dict(fila))


# ----------------------------------------------------------------

@app.route("/reservas/<int:reserva_id>/estado", methods=["PUT"])
def cambiar_estado(reserva_id):
    """
    Actualiza el estado de una reserva.

    Recibe (JSON):  { "estado": "confirmado" }
    Estados válidos: pendiente | confirmado | en camino | completado | cancelado
    """
    datos = request.get_json(silent=True)
    if not datos or "estado" not in datos:
        return jsonify({"error": "Falta el campo 'estado'."}), 400

    nuevo_estado = datos["estado"].strip().lower()
    if nuevo_estado not in ESTADOS_VALIDOS:
        return jsonify({"error": f"Estado no válido. Opciones: {ESTADOS_VALIDOS}"}), 400

    db   = get_db()
    fila = db.execute("SELECT id FROM reservas WHERE id = ?", (reserva_id,)).fetchone()
    if not fila:
        return jsonify({"error": f"Reserva #{reserva_id} no encontrada."}), 404

    db.execute("UPDATE reservas SET estado = ? WHERE id = ?", (nuevo_estado, reserva_id))
    db.commit()

    print(f"  🔄 Reserva #{reserva_id} → estado: {nuevo_estado}")
    return jsonify({"ok": True, "id": reserva_id, "estado": nuevo_estado})


# ----------------------------------------------------------------

@app.route("/reservas/<int:reserva_id>", methods=["DELETE"])
def cancelar_reserva(reserva_id):
    """Elimina (cancela) una reserva por ID."""
    db   = get_db()
    fila = db.execute("SELECT id, nombre FROM reservas WHERE id = ?", (reserva_id,)).fetchone()
    if not fila:
        return jsonify({"error": f"Reserva #{reserva_id} no encontrada."}), 404

    db.execute("DELETE FROM reservas WHERE id = ?", (reserva_id,))
    db.commit()

    print(f"  🗑️  Reserva #{reserva_id} eliminada ({fila['nombre']})")
    return jsonify({"ok": True, "mensaje": f"Reserva #{reserva_id} eliminada correctamente."})


# ================================================================
#  RUTA TARIFAS
# ================================================================

@app.route("/tarifa", methods=["POST"])
def calcular_tarifa():
    """
    Calcula la tarifa según la zona.

    Recibe (JSON):  { "zona": "Norte" }
    Devuelve (JSON): { zona, precio, tiempo, distancia }
    """
    datos = request.get_json(silent=True)
    if not datos:
        return jsonify({"error": "No se recibieron datos JSON."}), 400

    zona = datos.get("zona", "").strip()
    if zona not in TARIFAS:
        return jsonify({
            "error": "Zona no encontrada.",
            "zonas_disponibles": list(TARIFAS.keys())
        }), 404

    return jsonify({
        "zona":      zona,
        "precio":    TARIFAS[zona]["precio"],
        "tiempo":    TARIFAS[zona]["tiempo"],
        "distancia": TARIFAS[zona]["distancia"],
    })


@app.route("/tarifas", methods=["GET"])
def ver_todas_tarifas():
    """Devuelve todas las tarifas disponibles."""
    return jsonify(TARIFAS)


# ================================================================
#  ESTADÍSTICAS DEL NEGOCIO
# ================================================================

@app.route("/estadisticas", methods=["GET"])
def estadisticas():
    """
    Devuelve un resumen del negocio:
    - Total de reservas
    - Reservas por estado
    - Reservas por servicio
    - Ingresos totales y promedio
    - Reservas de hoy
    """
    db    = get_db()
    hoy   = datetime.now().strftime("%Y-%m-%d")

    total = db.execute("SELECT COUNT(*) FROM reservas").fetchone()[0]

    # Conteo por estado
    por_estado = {}
    for estado in ESTADOS_VALIDOS:
        n = db.execute("SELECT COUNT(*) FROM reservas WHERE estado = ?", (estado,)).fetchone()[0]
        por_estado[estado] = n

    # Conteo por tipo de servicio
    por_servicio = {}
    for serv in SERVICIOS_VALIDOS:
        n = db.execute("SELECT COUNT(*) FROM reservas WHERE servicio = ?", (serv,)).fetchone()[0]
        por_servicio[serv] = n

    # Ingresos (solo reservas completadas)
    fila_ing = db.execute(
        "SELECT SUM(precio), AVG(precio) FROM reservas WHERE estado = 'completado'"
    ).fetchone()
    ingresos_total   = round(fila_ing[0] or 0, 2)
    ingresos_promedio = round(fila_ing[1] or 0, 2)

    # Reservas de hoy
    hoy_total = db.execute(
        "SELECT COUNT(*) FROM reservas WHERE fecha = ?", (hoy,)
    ).fetchone()[0]

    return jsonify({
        "fecha_consulta":    hoy,
        "total_reservas":    total,
        "reservas_hoy":      hoy_total,
        "por_estado":        por_estado,
        "por_servicio":      por_servicio,
        "ingresos_completados": {
            "total":   ingresos_total,
            "promedio": ingresos_promedio,
            "moneda":  "Bs."
        }
    })


# ================================================================
#  EXPORTAR RESERVAS A ARCHIVO .TXT
# ================================================================

@app.route("/exportar", methods=["GET"])
def exportar():
    """
    Exporta todas las reservas a un archivo 'reservas.txt'
    en la misma carpeta del proyecto.
    """
    db    = get_db()
    filas = db.execute("SELECT * FROM reservas ORDER BY id").fetchall()

    ruta_txt = os.path.join(BASE_DIR, "reservas.txt")
    lineas   = []
    lineas.append("=" * 60)
    lineas.append("  MOTOÁPIDO — Reporte de Reservas")
    lineas.append(f"  Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lineas.append(f"  Total: {len(filas)} reservas")
    lineas.append("=" * 60)

    for f in filas:
        lineas.append("")
        lineas.append(f"  Reserva #{f['id']}  |  Estado: {f['estado'].upper()}")
        lineas.append(f"  Cliente : {f['nombre']}  ({f['telefono']})")
        lineas.append(f"  Ruta    : {f['origen']}  →  {f['destino']}")
        lineas.append(f"  Fecha   : {f['fecha']} a las {f['hora']}")
        lineas.append(f"  Servicio: {f['servicio']}  |  Precio: Bs. {f['precio']}")
        lineas.append(f"  Creado  : {f['creado']}")
        lineas.append("  " + "-" * 50)

    with open(ruta_txt, "w", encoding="utf-8") as archivo:
        archivo.write("\n".join(lineas))

    print(f"  📄 Exportado a: {ruta_txt}")
    return jsonify({
        "ok":    True,
        "archivo": ruta_txt,
        "total": len(filas),
        "mensaje": f"Se exportaron {len(filas)} reservas a 'reservas.txt'."
    })


# ================================================================
#  PANEL DE ADMINISTRACIÓN (HTML generado por Python)
# ================================================================

@app.route("/reservas/admin", methods=["GET"])
def panel_admin():
    """
    Panel HTML simple para ver y gestionar las reservas.
    Acceder en: http://127.0.0.1:5000/reservas/admin
    """
    db    = get_db()
    filas = db.execute("SELECT * FROM reservas ORDER BY id DESC").fetchall()
    total = len(filas)

    # Colores por estado
    colores = {
        "pendiente":  "#ff9800",
        "confirmado": "#2196f3",
        "en camino":  "#9c27b0",
        "completado": "#4caf50",
        "cancelado":  "#f44336",
    }

    filas_html = ""
    for f in filas:
        color = colores.get(f["estado"], "#999")
        filas_html += f"""
        <tr>
          <td>#{f['id']}</td>
          <td>{f['nombre']}</td>
          <td>{f['telefono']}</td>
          <td>{f['origen']}</td>
          <td>{f['destino']}</td>
          <td>{f['fecha']} {f['hora']}</td>
          <td>{f['servicio']}</td>
          <td><span style="background:{color};color:#fff;padding:3px 10px;
              border-radius:12px;font-size:0.82rem;font-weight:700">
              {f['estado']}</span></td>
          <td>Bs. {f['precio']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>MotoRapido — Panel Admin</title>
  <style>
    body{{font-family:Arial,sans-serif;margin:0;background:#f5f5f5;color:#333}}
    header{{background:#1a1a1a;color:#ff6b00;padding:18px 32px;
            display:flex;align-items:center;gap:12px}}
    header h1{{font-size:1.4rem;margin:0}}
    .contenido{{padding:28px 32px}}
    .stats{{display:flex;gap:16px;margin-bottom:28px;flex-wrap:wrap}}
    .stat{{background:#fff;border-radius:10px;padding:18px 28px;
           box-shadow:0 2px 8px rgba(0,0,0,.08);min-width:140px;text-align:center}}
    .stat__num{{font-size:2rem;font-weight:900;color:#ff6b00}}
    .stat__label{{font-size:.85rem;color:#777;margin-top:4px}}
    table{{width:100%;border-collapse:collapse;background:#fff;
           border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
    th{{background:#ff6b00;color:#fff;padding:12px 14px;
        text-align:left;font-size:.88rem}}
    td{{padding:11px 14px;font-size:.88rem;border-bottom:1px solid #f0f0f0}}
    tr:last-child td{{border-bottom:none}}
    tr:hover td{{background:#fff8f0}}
    .acciones{{margin-bottom:18px;display:flex;gap:12px;flex-wrap:wrap}}
    .btn{{padding:10px 22px;border:none;border-radius:8px;cursor:pointer;
          font-weight:700;font-size:.9rem;text-decoration:none;display:inline-block}}
    .btn-naranja{{background:#ff6b00;color:#fff}}
    .btn-naranja:hover{{background:#cc5500}}
    .btn-verde{{background:#4caf50;color:#fff}}
    .btn-verde:hover{{background:#388e3c}}
    .volver{{color:#ff6b00;font-size:.9rem;margin-bottom:16px;display:inline-block}}
  </style>
</head>
<body>
  <header>
    <span style="font-size:1.8rem">🏍️</span>
    <h1>MotoRapido — Panel de Administración</h1>
  </header>
  <div class="contenido">
    <a href="/" class="volver">← Volver al sitio</a>
    <div class="stats">
      <div class="stat">
        <div class="stat__num">{total}</div>
        <div class="stat__label">Total reservas</div>
      </div>
      <div class="stat">
        <div class="stat__num" style="color:#ff9800">
          {sum(1 for f in filas if f['estado']=='pendiente')}
        </div>
        <div class="stat__label">Pendientes</div>
      </div>
      <div class="stat">
        <div class="stat__num" style="color:#4caf50">
          {sum(1 for f in filas if f['estado']=='completado')}
        </div>
        <div class="stat__label">Completadas</div>
      </div>
      <div class="stat">
        <div class="stat__num" style="color:#f44336">
          {sum(1 for f in filas if f['estado']=='cancelado')}
        </div>
        <div class="stat__label">Canceladas</div>
      </div>
    </div>
    <div class="acciones">
      <a href="/estadisticas" class="btn btn-naranja" target="_blank">
        📊 Ver estadísticas JSON
      </a>
      <a href="/exportar" class="btn btn-verde" target="_blank">
        📄 Exportar a .txt
      </a>
      <a href="/reservas" class="btn btn-naranja" target="_blank">
        🔗 Ver reservas JSON
      </a>
    </div>
    <table>
      <thead>
        <tr>
          <th>ID</th><th>Cliente</th><th>Teléfono</th>
          <th>Origen</th><th>Destino</th><th>Fecha / Hora</th>
          <th>Servicio</th><th>Estado</th><th>Precio</th>
        </tr>
      </thead>
      <tbody>
        {filas_html if filas_html else
         '<tr><td colspan="9" style="text-align:center;color:#999;padding:40px">'
         'No hay reservas registradas aún.</td></tr>'}
      </tbody>
    </table>
  </div>
</body>
</html>"""
    return html


# ================================================================
#  MANEJO DE ERRORES
# ================================================================

@app.errorhandler(404)
def no_encontrado(e):
    return jsonify({"error": "Ruta no encontrada.", "codigo": 404}), 404


@app.errorhandler(405)
def metodo_no_permitido(e):
    return jsonify({"error": "Método HTTP no permitido.", "codigo": 405}), 405


@app.errorhandler(500)
def error_servidor(e):
    return jsonify({"error": "Error interno del servidor.", "detalle": str(e)}), 500

