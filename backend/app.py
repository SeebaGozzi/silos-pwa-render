import os
from datetime import datetime
import pytz
from flask import Flask, jsonify, request, send_from_directory, render_template
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, scoped_session
from sqlalchemy.exc import IntegrityError

# ---------- Config ----------
def get_database_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        # Render sometimes provides postgres://; SQLAlchemy needs postgresql://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        # Use psycopg (v3) driver explicitly for SQLAlchemy
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url
    # Fallback local SQLite for dev
    return "sqlite:///silos.db"

DATABASE_URL = get_database_url()

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))
Base = declarative_base()

# ---------- Models ----------
class Silo(Base):
    __tablename__ = "silos"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    cereal = Column(String(20), nullable=True)  # Soja, Maiz, Trigo, Girasol
    balance_kg = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    operations = relationship("Operation", back_populates="silo", cascade="all, delete")

    __table_args__ = (
        CheckConstraint("balance_kg >= 0", name="balance_non_negative"),
    )

class Operation(Base):
    __tablename__ = "operations"
    id = Column(Integer, primary_key=True)
    silo_id = Column(Integer, ForeignKey("silos.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(10), nullable=False)  # CARGA / DESCARGA
    amount = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    silo = relationship("Silo", back_populates="operations")

Base.metadata.create_all(engine)

# ---------- App ----------
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# Timezone for display (Argentina/Córdoba)
TZ = pytz.timezone("America/Argentina/Cordoba")

ALLOWED_CEREALES = {"Soja", "Maiz", "Trigo", "Girasol"}

def fmt_ts(dt: datetime) -> str:
    local_dt = dt.astimezone(TZ) if dt.tzinfo else TZ.localize(dt)
    return local_dt.strftime("%Y-%m-%d %H:%M")  # sin segundos

# ---------- API ----------
@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})

@app.get("/api/silos")
def list_silos():
    db = SessionLocal()
    try:
        silos = db.query(Silo).order_by(Silo.id).all()
        data = [
            {
                "id": s.id,
                "name": s.name,
                "cereal": s.cereal,
                "balance_kg": s.balance_kg,
                "created_at": fmt_ts(s.created_at if s.created_at.tzinfo else s.created_at.replace(tzinfo=pytz.utc)),
            }
            for s in silos
        ]
        return jsonify(data)
    finally:
        db.close()

@app.post("/api/silos")
def create_silo():
    db = SessionLocal()
    body = request.get_json(force=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "El nombre es obligatorio."}), 400
    try:
        s = Silo(name=name, cereal=None, balance_kg=0)
        db.add(s)
        db.commit()
        return jsonify({"message": f"Silo '{name}' creado correctamente.", "id": s.id}), 201
    except IntegrityError:
        db.rollback()
        return jsonify({"error": "Ya existe un silo con ese nombre."}), 409
    finally:
        db.close()

@app.patch("/api/silos/<int:silo_id>")
def rename_silo(silo_id):
    db = SessionLocal()
    body = request.get_json(force=True) or {}
    new_name = (body.get("name") or "").strip()
    if not new_name:
        db.close()
        return jsonify({"error": "El nuevo nombre es obligatorio."}), 400
    try:
        s = db.query(Silo).get(silo_id)
        if not s:
            db.close()
            return jsonify({"error": "Silo no encontrado."}), 404
        s.name = new_name
        db.commit()
        return jsonify({"message": "Nombre actualizado."})
    except IntegrityError:
        db.rollback()
        return jsonify({"error": "Ya existe un silo con ese nombre."}), 409
    finally:
        db.close()

@app.delete("/api/silos/<int:silo_id>")
def delete_silo(silo_id):
    db = SessionLocal()
    try:
        s = db.query(Silo).get(silo_id)
        if not s:
            return jsonify({"error": "Silo no encontrado."}), 404
        db.delete(s)
        db.commit()
        return jsonify({"message": "Silo eliminado."})
    finally:
        db.close()

@app.post("/api/silos/<int:silo_id>/cargar")
def cargar(silo_id):
    db = SessionLocal()
    body = request.get_json(force=True) or {}
    amount = int(body.get("amount") or 0)
    cereal = body.get("cereal")
    if amount <= 0:
        db.close()
        return jsonify({"error": "La cantidad debe ser mayor a 0."}), 400
    try:
        s = db.query(Silo).get(silo_id)
        if not s:
            return jsonify({"error": "Silo no encontrado."}), 404
        # Si el silo está vacío y no tiene cereal, hay que setearlo
        if s.balance_kg == 0 and (s.cereal is None):
            if not cereal or cereal not in ALLOWED_CEREALES:
                return jsonify({"error": "Debe seleccionar el cereal (Soja, Maiz, Trigo, Girasol)."}), 400
            s.cereal = cereal
        # Si ya tiene cereal, no permitir cambiar
        if s.cereal and cereal and cereal != s.cereal:
            return jsonify({"error": f"El silo ya almacena {s.cereal}. No puede cambiarse."}), 400
        s.balance_kg += amount
        op = Operation(silo_id=s.id, type="CARGA", amount=amount)
        db.add(op)
        db.commit()
        return jsonify({"message": "Carga registrada.", "balance_kg": s.balance_kg, "cereal": s.cereal})
    finally:
        db.close()

@app.post("/api/silos/<int:silo_id>/descargar")
def descargar(silo_id):
    db = SessionLocal()
    body = request.get_json(force=True) or {}
    amount = int(body.get("amount") or 0)
    if amount <= 0:
        db.close()
        return jsonify({"error": "La cantidad debe ser mayor a 0."}), 400
    try:
        s = db.query(Silo).get(silo_id)
        if not s:
            return jsonify({"error": "Silo no encontrado."}), 404
        if s.balance_kg - amount < 0:
            return jsonify({"error": "No hay suficiente stock en el silo."}), 400
        s.balance_kg -= amount
        op = Operation(silo_id=s.id, type="DESCARGA", amount=amount)
        db.add(op)
        db.commit()
        return jsonify({"message": "Descarga registrada.", "balance_kg": s.balance_kg})
    finally:
        db.close()

@app.get("/api/resumen")
def resumen():
    db = SessionLocal()
    try:
        ops = db.query(Operation).order_by(Operation.created_at.desc(), Operation.id.desc()).all()
        data = []
        for o in ops:
            data.append({
                "id": o.id,
                "silo_id": o.silo_id,
                "silo_name": o.silo.name if o.silo else None,
                "type": o.type,
                "amount": o.amount,
                "timestamp": fmt_ts(o.created_at if o.created_at.tzinfo else o.created_at.replace(tzinfo=pytz.utc)),
                "balance_kg_post": db.query(Silo).get(o.silo_id).balance_kg if o.silo_id else None,
            })
        return jsonify(data)
    finally:
        db.close()

# ---------- Frontend routes (serve React app) ----------
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    # Serve PWA static assets directly
    if path.startswith("icons/"):
        return send_from_directory("static", path)
    if path in ("manifest.json", "service-worker.js"):
        return send_from_directory("static", path)
    # Fallback to index.html (React SPA)
    return render_template("index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
