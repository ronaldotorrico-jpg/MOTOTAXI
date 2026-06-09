
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
    "Centro":     {"precio": 8,  "tiempo": "5–10 min",  "distancia": "0–3 km"},
    "Norte":      {"precio": 12, "tiempo": "10–15 min", "distancia": "3–6 km"},
    "Sur":        {"precio": 18, "tiempo": "15–25 min", "distancia": "6–10 km"},
    "Este/Oeste": {"precio": 25, "tiempo": "25–35 min", "distancia": "10–15 km"},
}

SERVICIOS_VALIDOS = ["viaje", "delivery", "mensajeria"]
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

