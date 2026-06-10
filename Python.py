
import sqlite3
import os
from flask import Flask, request, jsonify, g
from datetime import datetime

#  LÍDER 

# Carpeta donde está este archivo
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_RUTA  = os.path.join(BASE_DIR, "motorapido.db")

# Crear la aplicación Flask
# static_folder apunta a la misma carpeta para servir index.html y styles.css
app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")


# ── Base de datos SQLite ──────────────────────────────────────

def obtener_db():
    """
    Devuelve la conexión a la base de datos.
    Se crea una conexión por cada petición y se cierra al terminar.
    row_factory = sqlite3.Row permite acceder a las columnas por nombre.
    """
    if "db" not in g:
        g.db = sqlite3.connect(DB_RUTA)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def cerrar_db(error):
    """Cierra la conexión al terminar cada petición."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def crear_tablas():
    """
    Crea las tablas en la base de datos si no existen.
    Se ejecuta una sola vez al iniciar el servidor.
    """
    db = sqlite3.connect(DB_RUTA)

    # Tabla de reservas de viajes
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
            precio    REAL    NOT NULL DEFAULT 0,
            fecha_reg TEXT    NOT NULL
        )
    """)

    # Tabla de mensajes de contacto
    db.execute("""
        CREATE TABLE IF NOT EXISTS mensajes (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre    TEXT NOT NULL,
            email     TEXT NOT NULL,
            mensaje   TEXT NOT NULL,
            fecha_reg TEXT NOT NULL
        )
    """)

    db.commit()
    db.close()
    print("  ✅ Base de datos lista:", DB_RUTA)


# ── Datos del negocio ─────────────────────────────────────────

TARIFAS = {
    "Centro":     {"precio": 8,  "tiempo": "5–8 min",   "distancia": "0–3 km"},
    "Norte":      {"precio": 12, "tiempo": "8–15 min",  "distancia": "3–6 km"},
    "Sur":        {"precio": 20, "tiempo": "15–22 min", "distancia": "6–10 km"},
    "Este/Oeste": {"precio": 27, "tiempo": "22–35 min", "distancia": "10–15 km"},
}

SERVICIOS_VALIDOS = ["viaje", "delivery", "mensajeria", "encomienda"]
ESTADOS_VALIDOS   = ["pendiente", "confirmado", "en camino", "completado", "cancelado"]


# ── Función auxiliar ──────────────────────────────────────────

def fila_a_dict(fila):
    """Convierte una fila de SQLite a diccionario."""
    return dict(fila) if fila else None


# ── Ruta principal ────────────────────────────────────────────

@app.route("/")
def inicio():
    """
    Sirve la página principal (index.html).
    Flask busca el archivo en la carpeta definida en static_folder.
    """
    return app.send_static_file("index.html")

#  COLABORADOR 1 — JIMENA  Rutas: reservas, tarifas y estadísticas

# ── POST /reservar ────────────────────────────────────────────

@app.route("/reservar", methods=["POST"])
def reservar():
    """
    Recibe los datos del formulario HTML y guarda la reserva en SQLite.

    Espera JSON con:
        nombre, telefono, origen, destino, fecha, hora, servicio

    Devuelve JSON:
        { ok, mensaje, id, precio }
    """
    datos = request.get_json(silent=True)

    # Verificar que llegaron datos
    if not datos:
        return jsonify({"error": "No se recibieron datos."}), 400

    # Validar que todos los campos estén completos
    campos = ["nombre", "telefono", "origen", "destino", "fecha", "hora", "servicio"]
    for campo in campos:
        if not str(datos.get(campo, "")).strip():
            return jsonify({"error": f"El campo '{campo}' es obligatorio."}), 400

    # Validar que el servicio sea válido
    if datos["servicio"] not in SERVICIOS_VALIDOS:
        return jsonify({"error": f"Servicio no válido. Opciones: {SERVICIOS_VALIDOS}"}), 400

    # Validar formato de fecha (debe ser YYYY-MM-DD)
    try:
        datetime.strptime(datos["fecha"], "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Formato de fecha incorrecto. Use YYYY-MM-DD."}), 400

    # Calcular precio estimado según zona detectada
    texto_ruta = (datos["origen"] + " " + datos["destino"]).lower()
    if "norte" in texto_ruta:
        precio = TARIFAS["Norte"]["precio"]
    elif "sur" in texto_ruta:
        precio = TARIFAS["Sur"]["precio"]
    elif "este" in texto_ruta or "oeste" in texto_ruta:
        precio = TARIFAS["Este/Oeste"]["precio"]
    else:
        precio = TARIFAS["Centro"]["precio"]

    # Guardar en la base de datos
    db    = obtener_db()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor = db.execute(
        """
        INSERT INTO reservas
            (nombre, telefono, origen, destino, fecha, hora, servicio, precio, fecha_reg)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datos["nombre"].strip(),
            datos["telefono"].strip(),
            datos["origen"].strip(),
            datos["destino"].strip(),
            datos["fecha"].strip(),
            datos["hora"].strip(),
            datos["servicio"].strip(),
            precio,
            ahora,
        )
    )
    db.commit()
    nueva_id = cursor.lastrowid

    # Mostrar en la consola de VS Code
    print(f"\n  🏍️  Nueva reserva #{nueva_id}")
    print(f"     Cliente  : {datos['nombre']}  ({datos['telefono']})")
    print(f"     Ruta     : {datos['origen']}  →  {datos['destino']}")
    print(f"     Fecha    : {datos['fecha']} a las {datos['hora']}")
    print(f"     Servicio : {datos['servicio']}  |  Precio: Bs. {precio}\n")

    mensaje = (
        f"¡Gracias {datos['nombre']}! "
        f"Tu {datos['servicio']} de {datos['origen']} → {datos['destino']} "
        f"fue reservado para el {datos['fecha']} a las {datos['hora']}. "
        f"Precio estimado: Bs. {precio}. "
        f"Te contactamos al {datos['telefono']}."
    )

    return jsonify({"ok": True, "mensaje": mensaje, "id": nueva_id, "precio": precio})


# ── GET /reservas ─────────────────────────────────────────────

@app.route("/reservas", methods=["GET"])
def ver_reservas():
    """
    Devuelve todas las reservas en formato JSON.
    Filtros opcionales en la URL:
        /reservas?estado=pendiente
        /reservas?fecha=2025-06-15
    """
    db     = obtener_db()
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

    filas = db.execute(consulta, params).fetchall()
    lista = [fila_a_dict(f) for f in filas]

    return jsonify({"total": len(lista), "reservas": lista})


# ── GET /reservas/<id> ────────────────────────────────────────

@app.route("/reservas/<int:rid>", methods=["GET"])
def ver_reserva(rid):
    """Devuelve una reserva específica por su ID."""
    db   = obtener_db()
    fila = db.execute("SELECT * FROM reservas WHERE id = ?", (rid,)).fetchone()
    if not fila:
        return jsonify({"error": f"Reserva #{rid} no encontrada."}), 404
    return jsonify(fila_a_dict(fila))


# ── PUT /reservas/<id>/estado ─────────────────────────────────

@app.route("/reservas/<int:rid>/estado", methods=["PUT"])
def cambiar_estado(rid):
    """
    Cambia el estado de una reserva.
    Recibe JSON: { "estado": "confirmado" }
    Estados válidos: pendiente | confirmado | en camino | completado | cancelado
    """
    datos = request.get_json(silent=True)
    if not datos or "estado" not in datos:
        return jsonify({"error": "Falta el campo 'estado'."}), 400

    nuevo = datos["estado"].strip().lower()
    if nuevo not in ESTADOS_VALIDOS:
        return jsonify({"error": f"Estado no válido. Opciones: {ESTADOS_VALIDOS}"}), 400

    db = obtener_db()
    if not db.execute("SELECT id FROM reservas WHERE id = ?", (rid,)).fetchone():
        return jsonify({"error": f"Reserva #{rid} no encontrada."}), 404

    db.execute("UPDATE reservas SET estado = ? WHERE id = ?", (nuevo, rid))
    db.commit()

    print(f"  🔄 Reserva #{rid} → estado: {nuevo}")
    return jsonify({"ok": True, "id": rid, "estado": nuevo})


# ── DELETE /reservas/<id> ─────────────────────────────────────

@app.route("/reservas/<int:rid>", methods=["DELETE"])
def eliminar_reserva(rid):
    """Elimina una reserva por su ID."""
    db   = obtener_db()
    fila = db.execute("SELECT nombre FROM reservas WHERE id = ?", (rid,)).fetchone()
    if not fila:
        return jsonify({"error": f"Reserva #{rid} no encontrada."}), 404

    db.execute("DELETE FROM reservas WHERE id = ?", (rid,))
    db.commit()

    print(f"  🗑️  Reserva #{rid} eliminada.")
    return jsonify({"ok": True, "mensaje": f"Reserva #{rid} eliminada."})


# ── POST /tarifa ──────────────────────────────────────────────

@app.route("/tarifa", methods=["POST"])
def calcular_tarifa():
    """
    Calcula la tarifa según la zona indicada.
    Recibe JSON: { "zona": "Norte" }
    Devuelve: { zona, precio, tiempo, distancia }
    """
    datos = request.get_json(silent=True)
    if not datos:
        return jsonify({"error": "No se recibieron datos."}), 400

    zona = datos.get("zona", "").strip()
    if zona not in TARIFAS:
        return jsonify({
            "error": "Zona no válida.",
            "zonas": list(TARIFAS.keys())
        }), 404

    return jsonify({
        "zona":      zona,
        "precio":    TARIFAS[zona]["precio"],
        "tiempo":    TARIFAS[zona]["tiempo"],
        "distancia": TARIFAS[zona]["distancia"],
    })


# ── GET /tarifas ──────────────────────────────────────────────

@app.route("/tarifas", methods=["GET"])
def ver_tarifas():
    """Devuelve todas las zonas y tarifas disponibles."""
    return jsonify(TARIFAS)


# ── GET /estadisticas ─────────────────────────────────────────

@app.route("/estadisticas", methods=["GET"])
def estadisticas():
    """
    Devuelve un resumen del negocio:
      - Total de reservas y reservas de hoy
      - Conteo por estado y por tipo de servicio
      - Ingresos de viajes completados
    """
    db  = obtener_db()
    hoy = datetime.now().strftime("%Y-%m-%d")

    total     = db.execute("SELECT COUNT(*) FROM reservas").fetchone()[0]
    hoy_total = db.execute(
        "SELECT COUNT(*) FROM reservas WHERE fecha = ?", (hoy,)
    ).fetchone()[0]

    # Por estado
    por_estado = {}
    for estado in ESTADOS_VALIDOS:
        n = db.execute(
            "SELECT COUNT(*) FROM reservas WHERE estado = ?", (estado,)
        ).fetchone()[0]
        por_estado[estado] = n

    # Por tipo de servicio
    por_servicio = {}
    for serv in SERVICIOS_VALIDOS:
        n = db.execute(
            "SELECT COUNT(*) FROM reservas WHERE servicio = ?", (serv,)
        ).fetchone()[0]
        por_servicio[serv] = n

    # Ingresos solo de viajes completados
    fila_ing = db.execute(
        "SELECT SUM(precio), AVG(precio) FROM reservas WHERE estado = 'completado'"
    ).fetchone()
    total_ing   = round(fila_ing[0] or 0, 2)
    promedio_ing = round(fila_ing[1] or 0, 2)

    return jsonify({
        "fecha_consulta": hoy,
        "total_reservas": total,
        "reservas_hoy":   hoy_total,
        "por_estado":     por_estado,
        "por_servicio":   por_servicio,
        "ingresos": {
            "total":    total_ing,
            "promedio": promedio_ing,
            "moneda":   "Bs.",
            "nota":     "Solo reservas con estado 'completado'"
        }
    })
#  COLABORADOR 2 — ROGER Rutas: contacto, exportar y panel admin

# ── POST /contacto ────────────────────────────────────────────

@app.route("/contacto", methods=["POST"])
def guardar_mensaje():
    """
    Guarda un mensaje del formulario de contacto en la base de datos.
    Recibe JSON: { nombre, email, mensaje }
    """
    datos = request.get_json(silent=True)
    if not datos:
        return jsonify({"error": "No se recibieron datos."}), 400

    for campo in ["nombre", "email", "mensaje"]:
        if not str(datos.get(campo, "")).strip():
            return jsonify({"error": f"El campo '{campo}' es obligatorio."}), 400

    db    = obtener_db()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        "INSERT INTO mensajes (nombre, email, mensaje, fecha_reg) VALUES (?, ?, ?, ?)",
        (datos["nombre"].strip(), datos["email"].strip(),
         datos["mensaje"].strip(), ahora)
    )
    db.commit()

    print(f"\n  ✉️  Nuevo mensaje de contacto")
    print(f"     De      : {datos['nombre']} ({datos['email']})")
    print(f"     Mensaje : {datos['mensaje'][:60]}...\n")

    return jsonify({"ok": True, "mensaje": "Mensaje recibido. ¡Pronto te contactaremos!"})


# ── GET /mensajes ─────────────────────────────────────────────

@app.route("/mensajes", methods=["GET"])
def ver_mensajes():
    """Devuelve todos los mensajes de contacto recibidos."""
    db    = obtener_db()
    filas = db.execute("SELECT * FROM mensajes ORDER BY id DESC").fetchall()
    lista = [fila_a_dict(f) for f in filas]
    return jsonify({"total": len(lista), "mensajes": lista})


# ── GET /exportar ─────────────────────────────────────────────

@app.route("/exportar", methods=["GET"])
def exportar():
    """
    Exporta todas las reservas a un archivo reservas.txt
    en la misma carpeta del proyecto.
    Acceder en: http://127.0.0.1:5000/exportar
    """
    db    = obtener_db()
    filas = db.execute("SELECT * FROM reservas ORDER BY id").fetchall()

    ruta_txt = os.path.join(BASE_DIR, "reservas.txt")
    lineas   = [
        "=" * 60,
        "  MotoRapido — Reporte de Reservas",
        f"  Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Total   : {len(filas)} reservas",
        "=" * 60,
    ]

    for f in filas:
        lineas += [
            "",
            f"  Reserva #{f['id']}  |  Estado: {f['estado'].upper()}",
            f"  Cliente  : {f['nombre']}  ({f['telefono']})",
            f"  Ruta     : {f['origen']}  →  {f['destino']}",
            f"  Fecha    : {f['fecha']} a las {f['hora']}",
            f"  Servicio : {f['servicio']}  |  Precio: Bs. {f['precio']}",
            f"  Registrado: {f['fecha_reg']}",
            "  " + "-" * 50,
        ]

    with open(ruta_txt, "w", encoding="utf-8") as archivo:
        archivo.write("\n".join(lineas))

    print(f"  📄 Reservas exportadas a: {ruta_txt}")
    return jsonify({
        "ok":      True,
        "archivo": ruta_txt,
        "total":   len(filas),
        "mensaje": f"Se exportaron {len(filas)} reservas al archivo 'reservas.txt'."
    })


# ── GET /admin ────────────────────────────────────────────────

@app.route("/admin", methods=["GET"])
def panel_admin():
    """
    Panel de administración con interfaz HTML.
    Muestra todas las reservas con sus estados.
    Acceder en: http://127.0.0.1:5000/admin
    """
    db    = obtener_db()
    filas = db.execute("SELECT * FROM reservas ORDER BY id DESC").fetchall()
    total = len(filas)

    color_estado = {
        "pendiente":  "#ff9800",
        "confirmado": "#2196f3",
        "en camino":  "#9c27b0",
        "completado": "#4caf50",
        "cancelado":  "#f44336",
    }

    # Construir filas de la tabla HTML
    filas_html = ""
    for f in filas:
        color = color_estado.get(f["estado"], "#999999")
        filas_html += f"""
          <tr>
            <td>#{f['id']}</td>
            <td>{f['nombre']}</td>
            <td>{f['telefono']}</td>
            <td>{f['origen']}</td>
            <td>{f['destino']}</td>
            <td>{f['fecha']}<br><small>{f['hora']}</small></td>
            <td>{f['servicio']}</td>
            <td>
              <span style="background:{color};color:#fff;padding:3px 12px;
                border-radius:12px;font-size:0.8rem;font-weight:700;
                white-space:nowrap">
                {f['estado']}
              </span>
            </td>
            <td style="font-weight:700;color:#cc5500">Bs. {f['precio']}</td>
          </tr>"""

    if not filas_html:
        filas_html = """
          <tr>
            <td colspan="9" style="text-align:center;padding:50px;color:#aaa">
              No hay reservas registradas aún.
            </td>
          </tr>"""

    # Contar por estado para las estadísticas del panel
    def contar(estado):
        return sum(1 for f in filas if f["estado"] == estado)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>MotoRapido — Panel Admin</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',Arial,sans-serif;background:#f5f5f5;color:#333}}
    a{{text-decoration:none;color:inherit}}

    .topbar{{background:#1a1a1a;color:#ff6b00;padding:16px 36px;
             display:flex;align-items:center;gap:14px}}
    .topbar h1{{font-size:1.35rem;font-weight:900}}
    .topbar span{{font-size:1.7rem}}
    .volver{{margin-left:auto;color:#ccc;font-size:.9rem;
             padding:7px 16px;border:1px solid #444;border-radius:8px}}
    .volver:hover{{color:#ff6b00;border-color:#ff6b00}}

    .body{{padding:32px 36px}}

    .cards{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:30px}}
    .card{{background:#fff;border-radius:10px;padding:18px 28px;
           box-shadow:0 2px 10px rgba(0,0,0,.07);min-width:140px;text-align:center}}
    .card-num{{font-size:2rem;font-weight:900}}
    .card-label{{font-size:.82rem;color:#888;margin-top:4px}}

    .acciones{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px}}
    .btn{{padding:10px 22px;border-radius:8px;font-weight:700;
          font-size:.88rem;cursor:pointer;border:none}}
    .btn-naranja{{background:#ff6b00;color:#fff}}
    .btn-naranja:hover{{background:#cc5500}}
    .btn-verde{{background:#4caf50;color:#fff}}
    .btn-verde:hover{{background:#388e3c}}

    table{{width:100%;border-collapse:collapse;background:#fff;
           border-radius:10px;overflow:hidden;
           box-shadow:0 2px 10px rgba(0,0,0,.07)}}
    th{{background:#ff6b00;color:#fff;padding:13px 16px;
        text-align:left;font-size:.85rem;font-weight:700}}
    td{{padding:12px 16px;font-size:.85rem;border-bottom:1px solid #f0f0f0}}
    tr:last-child td{{border-bottom:none}}
    tr:hover td{{background:#fff8f0}}
  </style>
</head>
<body>

  <div class="topbar">
    <span>🏍️</span>
    <h1>MotoRapido — Panel de Administración</h1>
    <a href="/" class="volver">← Volver al sitio</a>
  </div>

  <div class="body">

    <!-- Tarjetas de resumen -->
    <div class="cards">
      <div class="card">
        <div class="card-num">{total}</div>
        <div class="card-label">Total reservas</div>
      </div>
      <div class="card">
        <div class="card-num" style="color:#ff9800">{contar('pendiente')}</div>
        <div class="card-label">Pendientes</div>
      </div>
      <div class="card">
        <div class="card-num" style="color:#2196f3">{contar('confirmado')}</div>
        <div class="card-label">Confirmadas</div>
      </div>
      <div class="card">
        <div class="card-num" style="color:#9c27b0">{contar('en camino')}</div>
        <div class="card-label">En camino</div>
      </div>
      <div class="card">
        <div class="card-num" style="color:#4caf50">{contar('completado')}</div>
        <div class="card-label">Completadas</div>
      </div>
      <div class="card">
        <div class="card-num" style="color:#f44336">{contar('cancelado')}</div>
        <div class="card-label">Canceladas</div>
      </div>
    </div>

    <!-- Acciones rápidas -->
    <div class="acciones">
      <a href="/estadisticas" target="_blank" class="btn btn-naranja">
        📊 Estadísticas JSON
      </a>
      <a href="/exportar" target="_blank" class="btn btn-verde">
        📄 Exportar a .txt
      </a>
      <a href="/tarifas" target="_blank" class="btn btn-naranja">
        💲 Ver tarifas JSON
      </a>
      <a href="/reservas" target="_blank" class="btn btn-naranja">
        📋 Reservas JSON
      </a>
    </div>

    <!-- Tabla de reservas -->
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Cliente</th>
          <th>Teléfono</th>
          <th>Origen</th>
          <th>Destino</th>
          <th>Fecha / Hora</th>
          <th>Servicio</th>
          <th>Estado</th>
          <th>Precio</th>
        </tr>
      </thead>
      <tbody>
        {filas_html}
      </tbody>
    </table>

  </div>
</body>
</html>"""

    return html


# ==============================================================
#  MANEJO DE ERRORES
# ==============================================================

@app.errorhandler(404)
def no_encontrado(e):
    return jsonify({"error": "Ruta no encontrada.", "codigo": 404}), 404


@app.errorhandler(500)
def error_servidor(e):
    return jsonify({"error": "Error interno del servidor.", "detalle": str(e)}), 500


# ==============================================================
#  INICIAR EL SERVIDOR
# ==============================================================

if __name__ == "__main__":
    crear_tablas()

    print()
    print("=" * 56)
    print("  🏍️  MotoRapido — Servidor corriendo")
    print("=" * 56)
    print("  Sitio web    →  http://127.0.0.1:5000")
    print("  Panel admin  →  http://127.0.0.1:5000/admin")
    print("  Estadísticas →  http://127.0.0.1:5000/estadisticas")
    print("  Tarifas      →  http://127.0.0.1:5000/tarifas")
    print("  Reservas     →  http://127.0.0.1:5000/reservas")
    print("  Exportar     →  http://127.0.0.1:5000/exportar")
    print("=" * 56)
    print()

    app.run(debug=True)


